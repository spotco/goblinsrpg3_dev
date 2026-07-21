const state = {
  manifest: null,
  screens: new Map(),
  current: null,
  muted: false,
  audioUnlocked: false,
  audioElements: new Map(),
  mediaBindings: new Map(),
  pendingAudioCommands: [],
  animations: null,
  animationSlides: new Map(),
  animationQueue: [],
  animationTimers: [],
  animationTriggerWaiters: new Map(),
  animationStartedNodes: new Set(),
  animationCompletedNodes: new Set(),
  currentLayerElements: new Map(),
  debug: new URLSearchParams(window.location.search).has("debug"),
};

const stage = document.getElementById("stage");
const screenImage = document.getElementById("screen");
const layersLayer = document.getElementById("layers");
const missingRender = document.getElementById("missing-render");
const hotspotsLayer = document.getElementById("hotspots");
const statusOutput = document.getElementById("status");
const restartButton = document.getElementById("restart");
const muteButton = document.getElementById("mute");

if (state.debug) {
  stage.classList.add("debug");
}

function screenId(slide) {
  return `slide-${String(slide).padStart(3, "0")}`;
}

function setStatus(text) {
  statusOutput.value = text;
  statusOutput.textContent = text;
}

function unlockAudio() {
  const wasLocked = !state.audioUnlocked;
  state.audioUnlocked = true;
  if (wasLocked) {
    flushPendingAudioCommands();
  }
}

function prepareAudio() {
  const audioEntries = state.manifest.audio || [];
  for (const entry of audioEntries) {
    if (!entry.outputs || entry.outputs.length === 0) {
      continue;
    }
    const preferred = entry.outputs.find((output) => output.type === "opus") || entry.outputs[0];
    const element = new Audio(preferred.path);
    element.preload = "auto";
    state.audioElements.set(entry.source, element);
  }
}

function stopAudio() {
  for (const element of state.audioElements.values()) {
    element.pause();
    element.currentTime = 0;
  }
}

function stopAudioExcept(sourceToKeep = null) {
  for (const [source, element] of state.audioElements.entries()) {
    if (source === sourceToKeep) {
      continue;
    }
    element.pause();
    element.currentTime = 0;
  }
}

function playAudioSource(source, startSeconds = 0, behavior = {}) {
  const element = state.audioElements.get(source);
  if (!element) {
    return;
  }
  if (!state.audioUnlocked) {
    state.pendingAudioCommands.push({ source, startSeconds, behavior });
    return;
  }
  if (behavior.stop) {
    stopAudioExcept(null);
    return;
  }
  if (behavior.replaceExisting !== false) {
    stopAudioExcept(source);
  }
  element.loop = Boolean(behavior.loop);
  element.pause();
  element.currentTime = Math.max(startSeconds, 0);
  element.play().catch(() => {
    // Browser autoplay policy can still reject in edge cases. Keep gameplay
    // running; the user can click again to unlock/resume audio.
  });
}

function flushPendingAudioCommands() {
  const pending = state.pendingAudioCommands.splice(0);
  for (const command of pending) {
    playAudioSource(command.source, command.startSeconds, command.behavior || {});
  }
}

function clearAnimationTimers() {
  for (const timer of state.animationTimers) {
    window.clearTimeout(timer);
  }
  state.animationTimers = [];
  state.animationQueue = [];
  state.animationTriggerWaiters = new Map();
  state.animationStartedNodes = new Set();
  state.animationCompletedNodes = new Set();
}

function scheduleAnimation(callback, delayMs = 0) {
  const timer = window.setTimeout(callback, Math.max(delayMs, 0));
  state.animationTimers.push(timer);
}

function updateAudioMute() {
  for (const element of state.audioElements.values()) {
    element.muted = state.muted;
  }
  muteButton.setAttribute("aria-pressed", String(state.muted));
  muteButton.textContent = state.muted ? "Unmute" : "Mute";
}

function navigateTo(id) {
  const next = state.screens.get(id);
  if (!next) {
    return;
  }
  state.current = next;
  renderScreen(next);
}

async function loadAnimations(manifest) {
  const animationStatus = manifest.animationStatus;
  if (!animationStatus || animationStatus.status !== "available" || !animationStatus.path) {
    return null;
  }
  const response = await fetch(animationStatus.path);
  if (!response.ok) {
    throw new Error(`Animation manifest load failed: ${response.status}`);
  }
  return response.json();
}

function mediaBindingForHotspot(hotspot) {
  if (hotspot.mediaBindingId) {
    return (state.manifest.mediaBindings || []).find((binding) => binding.id === hotspot.mediaBindingId) || null;
  }
  if (hotspot.shapeId === undefined || !state.current) {
    return null;
  }
  return state.mediaBindings.get(`${state.current.slide}:${hotspot.shapeId}`) || null;
}

function handleHotspotAction(hotspot) {
  unlockAudio();
  if (hotspot.action === "hyperlink" && hotspot.targetSlide) {
    navigateTo(screenId(hotspot.targetSlide));
    return;
  }
  if (hotspot.action === "media") {
    const binding = mediaBindingForHotspot(hotspot);
    if (binding && binding.status === "mapped" && binding.audioSource) {
      playAudioSource(binding.audioSource, binding.startSeconds || 0, binding.cueBehavior || {});
    }
  }
}

function renderHotspots(screen) {
  hotspotsLayer.replaceChildren();
  for (const hotspot of screen.hotspots || []) {
    if (!hotspot.bounds || !hotspot.clickable) {
      continue;
    }
    const button = document.createElement("button");
    const bounds = hotspot.bounds;
    button.type = "button";
    button.className = "hotspot";
    button.style.left = `${bounds.x * 100}%`;
    button.style.top = `${bounds.y * 100}%`;
    button.style.width = `${bounds.width * 100}%`;
    button.style.height = `${bounds.height * 100}%`;
    button.dataset.action = hotspot.action;
    if (hotspot.targetSlide) {
      button.dataset.target = screenId(hotspot.targetSlide);
    }
    button.setAttribute(
      "aria-label",
      hotspot.label || (hotspot.targetSlide ? `Go to slide ${hotspot.targetSlide}` : `Run ${hotspot.action} action`),
    );
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      handleHotspotAction(hotspot);
    });
    hotspotsLayer.append(button);
  }
}

function positionLayerElement(element, layer) {
  const bounds = layer.bounds;
  element.className = `layer layer-${layer.type}`;
  element.style.left = `${bounds.x * 100}%`;
  element.style.top = `${bounds.y * 100}%`;
  element.style.width = `${bounds.width * 100}%`;
  element.style.height = `${bounds.height * 100}%`;
  element.style.zIndex = String(layer.zOrder ?? 0);
  element.dataset.layerId = layer.id;
  element.dataset.shapeId = String(layer.shapeId);
  element.dataset.animated = String(Boolean(layer.animated));
  element.dataset.pptX = String(bounds.x);
  element.dataset.pptY = String(bounds.y);
  element.dataset.pptW = String(bounds.width);
  element.dataset.pptH = String(bounds.height);
  applyLayerTransform(element, layer);
  applyLayerVisualStyle(element, layer);
}

function pointWidthToContainer(value) {
  return `${(Number(value || 0) / 720) * 100}cqw`;
}

function pointHeightToContainer(value) {
  return `${(Number(value || 0) / 540) * 100}cqh`;
}

function pointFontToContainer(value) {
  return `${(Number(value || 1) / 540) * 100}cqh`;
}

function applyLayerTransform(element, layer) {
  const transform = layer.transform || {};
  const parts = [];
  if (Number.isFinite(transform.rotation) && transform.rotation !== 0) {
    parts.push(`rotate(${transform.rotation}deg)`);
  }
  const scaleX = transform.flipHorizontal ? -1 : 1;
  const scaleY = transform.flipVertical ? -1 : 1;
  if (scaleX !== 1 || scaleY !== 1) {
    parts.push(`scale(${scaleX}, ${scaleY})`);
  }
  const baseTransform = parts.join(" ");
  element.dataset.baseTransform = baseTransform;
  element.style.transform = baseTransform;
  element.style.transformOrigin = "center center";
}

function applyLayerVisualStyle(element, layer) {
  const style = layer.style || {};
  if (style.fillColor) {
    element.style.backgroundColor = style.fillColor;
  }
  if (style.lineColor && Number(style.lineWidth || 0) > 0) {
    element.style.border = `${style.lineWidth}pt solid ${style.lineColor}`;
  }
  if (style.lineDash && style.lineDash !== "SOLID") {
    element.style.borderStyle = "dashed";
  }
}

function applyTextLayerStyle(element, layer) {
  const textStyle = layer.textStyle || {};
  const firstRun = (layer.textRuns || [])[0] || {};
  const firstParagraph = (layer.paragraphs || [])[0] || {};
  element.style.display = "flex";
  element.style.paddingLeft = pointWidthToContainer(textStyle.leftInset);
  element.style.paddingRight = pointWidthToContainer(textStyle.rightInset);
  element.style.paddingTop = pointHeightToContainer(textStyle.topInset);
  element.style.paddingBottom = pointHeightToContainer(textStyle.bottomInset);
  element.style.whiteSpace = textStyle.wordWrap === false ? "pre" : "pre-wrap";
  element.style.overflowWrap = textStyle.wordWrap === false ? "normal" : "break-word";
  element.style.textAlign = String(firstParagraph.textAlign || "LEFT").toLowerCase();
  element.style.alignItems =
    textStyle.verticalAlignment === "MIDDLE" ? "center" : textStyle.verticalAlignment === "BOTTOM" ? "flex-end" : "flex-start";
  element.style.justifyContent = "flex-start";
  element.style.fontFamily = firstRun.fontFamily ? `"${firstRun.fontFamily}", Arial, sans-serif` : "Arial, sans-serif";
  if (Number.isFinite(firstRun.fontSize)) {
    element.style.fontSize = pointFontToContainer(firstRun.fontSize);
  } else {
    element.style.fontSize = `${Math.max(layer.bounds.height * 72, 1)}cqh`;
  }
  if (firstRun.fontColor) {
    element.style.color = firstRun.fontColor;
  }
  element.style.fontWeight = firstRun.bold ? "700" : "400";
  element.style.fontStyle = firstRun.italic ? "italic" : "normal";
  element.style.textDecoration = firstRun.underline ? "underline" : firstRun.strikethrough ? "line-through" : "none";
  if (Number.isFinite(firstParagraph.lineSpacing) && firstParagraph.lineSpacing > 0) {
    element.style.lineHeight = String(firstParagraph.lineSpacing / 100);
  }
}

function renderLayers(screen) {
  layersLayer.replaceChildren();
  state.currentLayerElements = new Map();
  const layers = screen.layers || [];
  for (const layer of layers) {
    const element = document.createElement("div");
    positionLayerElement(element, layer);
    if (layer.type === "image" && layer.instancePath) {
      const image = document.createElement("img");
      image.className = "layer-image";
      image.src = layer.instancePath;
      image.alt = "";
      image.decoding = "async";
      image.draggable = false;
      element.append(image);
    } else if (layer.type === "text") {
      element.textContent = layer.text || "";
      applyTextLayerStyle(element, layer);
    }
    state.currentLayerElements.set(String(layer.shapeId), element);
    layersLayer.append(element);
  }
  return layers.length > 0;
}

function parsedStrings(items) {
  const values = [];
  for (const item of items || []) {
    const parsed = item.parsed;
    if (parsed && typeof parsed.stringValue === "string") {
      values.push(parsed.stringValue);
    }
  }
  return values;
}

function parsedModifiers(node) {
  return (node.modifiers || []).map((modifier) => modifier.parsed).filter(Boolean);
}

function nodeParsed(node) {
  return (node.timeNode && node.timeNode.parsed) || {};
}

function hasModifier(node, modifierType) {
  return parsedModifiers(node).some((modifier) => modifier.modifierType === modifierType);
}

function modifierStrength(node, modifierType) {
  const modifier = parsedModifiers(node).find((item) => item.modifierType === modifierType);
  if (!modifier) {
    return 0;
  }
  return Number.isFinite(modifier.floatValue) ? modifier.floatValue : 1;
}

function metricFor(element, property) {
  const key = {
    ppt_x: "pptX",
    ppt_y: "pptY",
    ppt_w: "pptW",
    ppt_h: "pptH",
  }[property];
  return key ? Number.parseFloat(element.dataset[key] || "0") : 0;
}

function setMetric(element, property, value) {
  const numeric = Number.isFinite(value) ? value : 0;
  if (property === "ppt_x") {
    element.dataset.pptX = String(numeric);
    element.style.left = `${numeric * 100}%`;
  } else if (property === "ppt_y") {
    element.dataset.pptY = String(numeric);
    element.style.top = `${numeric * 100}%`;
  } else if (property === "ppt_w") {
    element.dataset.pptW = String(numeric);
    element.style.width = `${numeric * 100}%`;
  } else if (property === "ppt_h") {
    element.dataset.pptH = String(numeric);
    element.style.height = `${numeric * 100}%`;
  }
}

function evaluatePowerPointFormula(expression, element) {
  if (typeof expression !== "string" || !expression.trim()) {
    return null;
  }
  let formula = expression.trim().replace(/#/g, "");
  if (formula.startsWith("(") && formula.endsWith(")")) {
    formula = formula.slice(1, -1);
  }
  formula = formula.replace(/\bppt_x\b/g, String(metricFor(element, "ppt_x")));
  formula = formula.replace(/\bppt_y\b/g, String(metricFor(element, "ppt_y")));
  formula = formula.replace(/\bppt_w\b/g, String(metricFor(element, "ppt_w")));
  formula = formula.replace(/\bppt_h\b/g, String(metricFor(element, "ppt_h")));
  if (!/^[\d+\-*/(). eE]+$/.test(formula)) {
    return null;
  }
  try {
    const value = Function(`"use strict"; return (${formula});`)();
    return Number.isFinite(value) ? value : null;
  } catch (_error) {
    return null;
  }
}

function propertyNameFromStrings(strings) {
  for (let index = strings.length - 1; index >= 0; index -= 1) {
    if (/^ppt_[xywh]$/.test(strings[index])) {
      return strings[index];
    }
  }
  return null;
}

function formulaStrings(strings, property) {
  return strings.filter((value) => {
    if (!value || value === property || value.startsWith("M ") || value.includes(";")) {
      return false;
    }
    return value.includes("#") || value.includes("ppt_") || /^[(]?[+\-]?\d/.test(value);
  });
}

function nodeDelay(node) {
  let delay = 0;
  for (const condition of node.conditions || []) {
    const parsed = condition.parsed;
    if (parsed && parsed.triggerObject === 2 && (parsed.triggerEvent === 3 || parsed.triggerEvent === 4)) {
      continue;
    }
    if (parsed && Number.isFinite(parsed.delayMs) && parsed.delayMs > delay) {
      delay = parsed.delayMs;
    }
  }
  return delay;
}

function nodeUsesHoldFill(node) {
  const parsed = nodeParsed(node);
  return parsed.usesFill === true && parsed.fill === 3;
}

function nodeRestartMode(node) {
  const parsed = nodeParsed(node);
  return Number.isFinite(parsed.restart) ? parsed.restart : 0;
}

function nodeLocalId(node) {
  const match = typeof node.id === "string" ? node.id.match(/tn(\d+)$/) : null;
  return match ? Number.parseInt(match[1], 10) : null;
}

function triggerKey(triggerEvent, targetId) {
  return `${triggerEvent}:${targetId}`;
}

function nodeTriggerConditions(node) {
  return (node.conditions || [])
    .map((condition) => condition.parsed)
    .filter((condition) => {
      return (
        condition &&
        condition.triggerObject === 2 &&
        (condition.triggerEvent === 3 || condition.triggerEvent === 4) &&
        Number.isFinite(condition.targetId) &&
        condition.targetId > 0
      );
    });
}

function registerAnimationTriggerWaits(node) {
  for (const condition of nodeTriggerConditions(node)) {
    const key = triggerKey(condition.triggerEvent, condition.targetId);
    const waiters = state.animationTriggerWaiters.get(key) || [];
    waiters.push({
      node,
      delayMs: Number.isFinite(condition.delayMs) && condition.delayMs > 0 ? condition.delayMs : 0,
    });
    state.animationTriggerWaiters.set(key, waiters);
  }
}

function emitAnimationTrigger(triggerEvent, node) {
  const localId = nodeLocalId(node);
  if (!localId) {
    return;
  }
  const key = triggerKey(triggerEvent, localId);
  const waiters = state.animationTriggerWaiters.get(key);
  if (!waiters || waiters.length === 0) {
    return;
  }
  state.animationTriggerWaiters.delete(key);
  for (const waiter of waiters) {
    runAnimationNode(waiter.node, waiter.delayMs, true, true);
  }
}

function nodeWaitsForClick(node) {
  return (node.conditions || []).some((condition) => {
    const event = condition.parsed && condition.parsed.triggerEvent;
    return event === 9 || event === 10;
  });
}

function targetsFor(node, behavior) {
  const targets = behavior.targets && behavior.targets.length ? behavior.targets : node.targets || [];
  return targets
    .filter((target) => target.kind === "shape" && target.shapeId !== undefined)
    .map((target) => state.currentLayerElements.get(String(target.shapeId)))
    .filter(Boolean);
}

function nodeDuration(node) {
  const parsed = nodeParsed(node);
  if (!parsed || !Number.isFinite(parsed.durationMs) || parsed.durationMs <= 1) {
    return 1;
  }
  return parsed.durationMs;
}

function nodeTiming(node) {
  const duration = nodeDuration(node);
  const acceleration = modifierStrength(node, 3);
  const deceleration = modifierStrength(node, 4);
  let timingFunction = "linear";
  if (acceleration > 0 && deceleration > 0) {
    timingFunction = "ease-in-out";
  } else if (acceleration > 0) {
    timingFunction = "ease-in";
  } else if (deceleration > 0) {
    timingFunction = "ease-out";
  }
  return {
    duration,
    timingFunction,
    autoReverse: hasModifier(node, 5),
    holdFill: nodeUsesHoldFill(node),
  };
}

function nodeSequenceData(node) {
  return (node.sequence && node.sequence.parsed) || null;
}

function nodeChildrenRunOnClick(node) {
  const sequence = nodeSequenceData(node);
  return Boolean(sequence && sequence.usesNextAction && sequence.nextAction === 1 && (node.children || []).length > 1);
}

function nodeRunsSequentialChildren(node) {
  const sequence = nodeSequenceData(node);
  return Boolean(sequence && sequence.usesConcurrency && sequence.concurrency === 0);
}

function subtreeDuration(node) {
  const children = node.children || [];
  if (!children.length) {
    return nodeDelay(node) + nodeDuration(node);
  }
  if (nodeRunsSequentialChildren(node)) {
    return children.reduce((total, child) => total + subtreeDuration(child), nodeDelay(node) + nodeDuration(node));
  }
  return nodeDelay(node) + Math.max(nodeDuration(node), ...children.map((child) => subtreeDuration(child)));
}

function transitionList(properties, timing) {
  return properties.map((property) => `${property} ${timing.duration}ms ${timing.timingFunction}`).join(", ");
}

function applySetBehavior(elements, strings) {
  if (!strings.includes("style.visibility")) {
    return;
  }
  const visibility = strings.includes("hidden") ? "hidden" : strings.includes("visible") ? "visible" : null;
  if (!visibility) {
    return;
  }
  for (const element of elements) {
    element.style.visibility = visibility;
    if (visibility === "visible") {
      element.style.opacity = element.style.opacity || "1";
    }
  }
}

function applyEffectBehavior(elements, strings, timing) {
  if (!strings.some((value) => value === "fade" || value === "dissolve")) {
    return;
  }
  for (const element of elements) {
    const originalOpacity = element.style.opacity;
    const originalVisibility = element.style.visibility;
    element.style.visibility = "visible";
    element.style.opacity = "0";
    element.style.transition = transitionList(["opacity"], timing);
    window.requestAnimationFrame(() => {
      element.style.opacity = "1";
    });
    if (timing.autoReverse) {
      scheduleAnimation(() => {
        element.style.opacity = "0";
      }, timing.duration);
    } else if (!timing.holdFill) {
      scheduleAnimation(() => {
        element.style.opacity = originalOpacity;
        element.style.visibility = originalVisibility;
      }, timing.duration);
    }
  }
}

function applyAnimateBehavior(elements, strings, timing) {
  const property = propertyNameFromStrings(strings);
  if (!property) {
    return;
  }
  const formulas = formulaStrings(strings, property);
  const targetFormula = formulas[formulas.length - 1];
  for (const element of elements) {
    const target = evaluatePowerPointFormula(targetFormula, element);
    if (target === null) {
      continue;
    }
    const original = metricFor(element, property);
    element.style.transition =
      property === "ppt_x" || property === "ppt_y"
        ? transitionList(["left", "top"], timing)
        : transitionList(["width", "height"], timing);
    window.requestAnimationFrame(() => {
      setMetric(element, property, target);
    });
    if (timing.autoReverse) {
      scheduleAnimation(() => {
        setMetric(element, property, original);
      }, timing.duration);
    } else if (!timing.holdFill) {
      scheduleAnimation(() => {
        setMetric(element, property, original);
      }, timing.duration);
    }
  }
}

function motionEndpoint(path) {
  if (typeof path !== "string" || !path.startsWith("M ")) {
    return null;
  }
  const numbers = path.match(/[+\-]?(?:\d+\.?\d*|\.\d+)(?:E[+\-]?\d+)?/gi)?.map(Number) || [];
  if (numbers.length < 4) {
    return null;
  }
  return { x: numbers[numbers.length - 2], y: numbers[numbers.length - 1] };
}

function applyMotionBehavior(elements, strings, timing) {
  const path = strings.find((value) => value.startsWith("M "));
  const endpoint = motionEndpoint(path);
  if (!endpoint) {
    return;
  }
  for (const element of elements) {
    const originalTransform = element.style.transform;
    element.style.transition = transitionList(["transform"], timing);
    window.requestAnimationFrame(() => {
      const baseTransform = element.dataset.baseTransform || "";
      element.style.transform = `${baseTransform} translate(${endpoint.x * 100}cqw, ${endpoint.y * 100}cqh)`.trim();
    });
    if (timing.autoReverse) {
      scheduleAnimation(() => {
        element.style.transform = originalTransform;
      }, timing.duration);
    } else if (!timing.holdFill) {
      scheduleAnimation(() => {
        element.style.transform = originalTransform;
      }, timing.duration);
    }
  }
}

function littleEndianFloatFromHex(hex, offset) {
  if (typeof hex !== "string" || hex.length < offset * 2 + 8) {
    return null;
  }
  const bytes = new Uint8Array(4);
  for (let index = 0; index < 4; index += 1) {
    bytes[index] = Number.parseInt(hex.slice((offset + index) * 2, (offset + index + 1) * 2), 16);
  }
  return new DataView(bytes.buffer).getFloat32(0, true);
}

function scaleTargetFromBehavior(behavior) {
  const atom = (behavior.atoms || []).find((item) => item.type === 61753 && typeof item.payloadHex === "string");
  if (!atom) {
    return null;
  }
  const x = littleEndianFloatFromHex(atom.payloadHex, 20);
  const y = littleEndianFloatFromHex(atom.payloadHex, 24);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }
  return { x: x / 100, y: y / 100 };
}

function applyScaleBehavior(elements, behavior, timing) {
  const target = scaleTargetFromBehavior(behavior);
  if (!target) {
    return;
  }
  for (const element of elements) {
    const originalTransform = element.style.transform;
    element.style.transition = transitionList(["transform"], timing);
    window.requestAnimationFrame(() => {
      const baseTransform = element.dataset.baseTransform || "";
      element.style.transform = `${baseTransform} scale(${target.x}, ${target.y})`.trim();
    });
    if (timing.autoReverse || !timing.holdFill) {
      scheduleAnimation(() => {
        element.style.transform = originalTransform;
      }, timing.duration);
    }
  }
}

function applyCommandBehavior(node, behavior, strings) {
  if (!strings.some((value) => value.startsWith("playFrom"))) {
    return;
  }
  const targets = behavior.targets && behavior.targets.length ? behavior.targets : node.targets || [];
  const startMatch = strings.find((value) => value.startsWith("playFrom"))?.match(/playFrom\\(([-+\\d.]+)\\)/);
  const startSeconds = startMatch ? Number.parseFloat(startMatch[1]) : 0;
  for (const target of targets) {
    if (target.kind !== "shape") {
      continue;
    }
    const binding = state.mediaBindings.get(`${state.current.slide}:${target.shapeId}`);
    if (binding && binding.status === "mapped" && binding.audioSource) {
      playAudioSource(binding.audioSource, startSeconds, binding.cueBehavior || {});
    }
  }
}

function applyBehavior(node, behavior) {
  const strings = parsedStrings(behavior.variants);
  const timing = nodeTiming(node);
  if (behavior.kind === "command") {
    applyCommandBehavior(node, behavior, strings);
    return;
  }
  const elements = targetsFor(node, behavior);
  if (elements.length === 0) {
    return;
  }
  if (behavior.kind === "set") {
    applySetBehavior(elements, strings);
  } else if (behavior.kind === "effect") {
    applyEffectBehavior(elements, strings, timing);
  } else if (behavior.kind === "animate") {
    applyAnimateBehavior(elements, strings, timing);
  } else if (behavior.kind === "motion") {
    applyMotionBehavior(elements, strings, timing);
  } else if (behavior.kind === "scale") {
    applyScaleBehavior(elements, behavior, timing);
  }
}

function runAnimationNode(node, baseDelay = 0, allowClickNode = false, allowTriggeredNode = false) {
  if (state.animationCompletedNodes.has(node.id) && nodeRestartMode(node) === 0 && !allowTriggeredNode && !allowClickNode) {
    return;
  }
  if (nodeTriggerConditions(node).length > 0 && !allowTriggeredNode) {
    registerAnimationTriggerWaits(node);
    return;
  }
  if (nodeWaitsForClick(node) && !allowClickNode) {
    state.animationQueue.push(node);
    return;
  }
  const startDelay = baseDelay + nodeDelay(node);
  scheduleAnimation(() => {
    state.animationStartedNodes.add(node.id);
    emitAnimationTrigger(3, node);
  }, startDelay);
  if (node.behaviors && node.behaviors.length) {
    scheduleAnimation(() => {
      for (const behavior of node.behaviors) {
        applyBehavior(node, behavior);
      }
    }, startDelay);
  }
  scheduleAnimation(() => {
    state.animationCompletedNodes.add(node.id);
    emitAnimationTrigger(4, node);
  }, startDelay + nodeDuration(node));
  scheduleChildNodes(node, startDelay);
}

function scheduleChildNodes(node, startDelay) {
  const children = node.children || [];
  if (!children.length) {
    return;
  }
  if (nodeChildrenRunOnClick(node)) {
    for (const child of children) {
      state.animationQueue.push(child);
    }
    return;
  }
  if (nodeRunsSequentialChildren(node)) {
    let childDelay = 0;
    for (const child of children) {
      runAnimationNode(child, startDelay + childDelay, false, false);
      childDelay += subtreeDuration(child);
    }
    return;
  }
  for (const child of children) {
    runAnimationNode(child, startDelay, false, false);
  }
}

function setupAnimations(screen) {
  clearAnimationTimers();
  for (const element of state.currentLayerElements.values()) {
    element.style.visibility = "";
    element.style.opacity = "";
    element.style.transition = "";
    element.style.transform = element.dataset.baseTransform || "";
  }
  const slideAnimations = state.animationSlides.get(screen.slide);
  if (!slideAnimations) {
    return;
  }
  for (const node of slideAnimations.rootTimeNodes || []) {
    runAnimationNode(node, 0, false);
  }
}

function advanceAnimation() {
  const node = state.animationQueue.shift();
  if (!node) {
    return false;
  }
  runAnimationNode(node, 0, true);
  return true;
}

function renderScreen(screen) {
  const slideNumber = String(screen.slide).padStart(3, "0");
  const renderedLayers = renderLayers(screen);
  screenImage.alt = `Screen ${slideNumber}`;
  screenImage.src = screen.image;
  screenImage.hidden = renderedLayers;
  layersLayer.hidden = !renderedLayers;
  missingRender.hidden = true;
  setupAnimations(screen);
  applySlideTransition(screen);
  renderHotspots(screen);
  setStatus(`Screen ${slideNumber}`);
}

function transitionDuration(screen) {
  const speed = screen.transition && screen.transition.speed;
  if (speed === 0) {
    return 900;
  }
  if (speed === 1) {
    return 650;
  }
  return 400;
}

function transitionEffectClass(transition) {
  const effectType = transition && transition.effectType;
  if (!effectType) {
    return null;
  }
  return `transition-effect-${effectType}`;
}

function transitionDirectionClass(transition) {
  const direction = transition && transition.effectDirection;
  return Number.isFinite(direction) ? `transition-direction-${direction}` : "transition-direction-0";
}

function clearSlideTransitionClasses() {
  for (const className of Array.from(stage.classList)) {
    if (className.startsWith("transition-effect-") || className.startsWith("transition-direction-")) {
      stage.classList.remove(className);
    }
  }
}

function applySlideTransition(screen) {
  const transition = screen.transition;
  if (!transition || transition.effectType === 0) {
    clearSlideTransitionClasses();
    return;
  }
  stage.style.setProperty("--transition-duration", `${transitionDuration(screen)}ms`);
  clearSlideTransitionClasses();
  stage.classList.add(transitionEffectClass(transition), transitionDirectionClass(transition));
  stage.classList.remove("is-transitioning");
  void stage.offsetWidth;
  stage.classList.add("is-transitioning");
  scheduleAnimation(() => {
    stage.classList.remove("is-transitioning");
    clearSlideTransitionClasses();
  }, transitionDuration(screen));
}

screenImage.addEventListener("error", () => {
  screenImage.hidden = true;
  missingRender.hidden = false;
});

stage.addEventListener("click", () => {
  unlockAudio();
  advanceAnimation();
});

restartButton.addEventListener("click", () => {
  unlockAudio();
  stopAudio();
  navigateTo(state.manifest.startScreen);
});

muteButton.addEventListener("click", () => {
  state.muted = !state.muted;
  updateAudioMute();
});

fetch("game-manifest.json")
  .then((response) => {
    if (!response.ok) {
      throw new Error(`Manifest load failed: ${response.status}`);
    }
    return response.json();
  })
  .then((manifest) => {
    state.manifest = manifest;
    state.screens = new Map(manifest.screens.map((screen) => [screen.id, screen]));
    state.mediaBindings = new Map((manifest.mediaBindings || []).map((binding) => [`${binding.slide}:${binding.shapeId}`, binding]));
    prepareAudio();
    updateAudioMute();
    return loadAnimations(manifest).then((animations) => {
      state.animations = animations;
      state.animationSlides = new Map((animations?.slides || []).map((slide) => [slide.slide, slide]));
      navigateTo(manifest.startScreen);
    });
  })
  .catch((error) => {
    setStatus(error.message);
    missingRender.hidden = false;
  });
