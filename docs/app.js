// Runtime diagnostics configuration. Change loggingEnabled and reload the page
// when detailed browser-console tracing is needed.
const RUNTIME_CONFIG = Object.freeze({
  loggingEnabled: false,
  debugCssEnabled: false,
});

const ASSET_CACHE_BUSTER = String(Date.now());

function assetUrl(path) {
  if (!path || /^(data:|blob:|https?:)/i.test(path)) {
    return path;
  }
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}no-cache=${ASSET_CACHE_BUSTER}`;
}

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
  debug: RUNTIME_CONFIG.debugCssEnabled,
  logging: RUNTIME_CONFIG.loggingEnabled,
  logSequence: 0,
  loggerStartedAt: typeof performance !== "undefined" ? performance.now() : Date.now(),
  animationTimerSequence: 0,
  autoAdvanceTimer: null,
  autoAdvanceSequence: 0,
};

const stage = document.getElementById("stage");
const screenImage = document.getElementById("screen");
const layersLayer = document.getElementById("layers");
const missingRender = document.getElementById("missing-render");
const hotspotsLayer = document.getElementById("hotspots");
const statusOutput = document.getElementById("status");
const restartButton = document.getElementById("restart");
const muteButton = document.getElementById("mute");

function runtimeLog(event, details = {}, level = "info") {
  if (!state.logging || typeof console === "undefined") {
    return;
  }
  const now = typeof performance !== "undefined" ? performance.now() : Date.now();
  const currentScreen = state.current
    ? { id: state.current.id, slide: state.current.slide }
    : null;
  const payload = {
    sequence: ++state.logSequence,
    elapsedMs: Math.round((now - state.loggerStartedAt) * 10) / 10,
    event,
    currentScreen,
    ...details,
  };
  const method = typeof console[level] === "function" ? console[level].bind(console) : console.log.bind(console);
  method(`[GoblinsRPG3] ${event}`, payload);
}

function animationNodeInfo(node) {
  if (!node) {
    return null;
  }
  return {
    id: node.id,
    localId: nodeLocalId(node),
    delayMs: nodeDelay(node),
    durationMs: nodeDuration(node),
    behaviorCount: (node.behaviors || []).length,
    childCount: (node.children || []).length,
    waitsForClick: nodeWaitsForClick(node),
    triggerConditions: nodeTriggerConditions(node).map((condition) => ({
      triggerEvent: condition.triggerEvent,
      targetId: condition.targetId,
      delayMs: condition.delayMs,
    })),
  };
}

window.goblinsRpg3Debug = {
  get enabled() {
    return state.logging;
  },
  setEnabled(enabled) {
    const nextEnabled = Boolean(enabled);
    const previousEnabled = state.logging;
    if (previousEnabled && !nextEnabled) {
      runtimeLog("logging:toggled", { enabled: false });
    }
    state.logging = nextEnabled;
    if (!previousEnabled && nextEnabled) {
      runtimeLog("logging:toggled", { enabled: true });
    }
    return nextEnabled;
  },
  toggle() {
    return window.goblinsRpg3Debug.setEnabled(!state.logging);
  },
  snapshot() {
    return {
      loggingEnabled: state.logging,
      debugCssEnabled: state.debug,
      currentScreen: state.current ? { id: state.current.id, slide: state.current.slide } : null,
      queuedAnimationNodes: state.animationQueue.map((node) => animationNodeInfo(node)),
      trackedAnimationTimerHandles: state.animationTimers.length,
      startedAnimationNodes: state.animationStartedNodes.size,
      completedAnimationNodes: state.animationCompletedNodes.size,
      animationTriggerWaiters: Array.from(state.animationTriggerWaiters.entries()).map(([key, waiters]) => ({
        key,
        count: waiters.length,
        nodes: waiters.map((waiter) => animationNodeInfo(waiter.node)),
      })),
    };
  },
};

runtimeLog("runtime:initialized", {
  url: window.location.href,
  debugCssEnabled: state.debug,
  loggingEnabled: state.logging,
  loggingControls: "window.goblinsRpg3Debug.toggle() / setEnabled(true|false) / snapshot()",
});

if (state.debug) {
  stage.classList.add("debug");
}

function screenId(slide) {
  return `slide-${String(slide).padStart(3, "0")}`;
}

function setStatus(text) {
  statusOutput.value = text;
  statusOutput.textContent = text;
  runtimeLog("ui:status", { text });
}

function unlockAudio() {
  const wasLocked = !state.audioUnlocked;
  state.audioUnlocked = true;
  runtimeLog("audio:unlock", { wasLocked, pendingCommands: state.pendingAudioCommands.length });
  if (wasLocked) {
    flushPendingAudioCommands();
  }
}

function prepareAudio() {
  const audioEntries = state.manifest.audio || [];
  let preparedCount = 0;
  for (const entry of audioEntries) {
    if (!entry.outputs || entry.outputs.length === 0) {
      runtimeLog("audio:skip-entry", { source: entry.source, reason: "no outputs" }, "warn");
      continue;
    }
    const preferred = entry.outputs.find((output) => output.type === "opus") || entry.outputs[0];
    const element = new Audio(assetUrl(preferred.path));
    element.preload = "auto";
    state.audioElements.set(entry.source, element);
    preparedCount += 1;
  }
  runtimeLog("audio:prepared", { manifestEntries: audioEntries.length, preparedCount });
}

function stopAudio() {
  runtimeLog("audio:stop-all", { count: state.audioElements.size });
  for (const element of state.audioElements.values()) {
    element.pause();
    element.currentTime = 0;
  }
}

function stopAudioExcept(sourceToKeep = null) {
  runtimeLog("audio:stop-except", { sourceToKeep, count: state.audioElements.size });
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
    runtimeLog("audio:missing-source", { source, startSeconds, behavior }, "warn");
    return;
  }
  if (!state.audioUnlocked) {
    state.pendingAudioCommands.push({ source, startSeconds, behavior });
    runtimeLog("audio:queued-before-unlock", {
      source,
      startSeconds,
      behavior,
      pendingCommands: state.pendingAudioCommands.length,
    });
    return;
  }
  if (behavior.stop) {
    runtimeLog("audio:command-stop", { source, startSeconds, behavior });
    stopAudioExcept(null);
    return;
  }
  if (behavior.replaceExisting !== false) {
    stopAudioExcept(source);
  }
  element.loop = Boolean(behavior.loop);
  element.pause();
  element.currentTime = Math.max(startSeconds, 0);
  runtimeLog("audio:play", {
    source,
    startSeconds: Math.max(startSeconds, 0),
    loop: element.loop,
    behavior,
  });
  element.play().catch(() => {
    runtimeLog("audio:play-rejected", { source, startSeconds, behavior }, "warn");
    // Browser autoplay policy can still reject in edge cases. Keep gameplay
    // running; the user can click again to unlock/resume audio.
  });
}

function flushPendingAudioCommands() {
  const pending = state.pendingAudioCommands.splice(0);
  runtimeLog("audio:flush-pending", { count: pending.length });
  for (const command of pending) {
    playAudioSource(command.source, command.startSeconds, command.behavior || {});
  }
}

function clearAutoAdvanceTimer(reason = "unspecified") {
  if (state.autoAdvanceTimer === null) {
    return;
  }
  window.clearTimeout(state.autoAdvanceTimer.handle);
  runtimeLog("navigation:auto-advance-cleared", {
    timerId: state.autoAdvanceTimer.id,
    reason,
    fromScreen: state.autoAdvanceTimer.fromScreen,
    toScreen: state.autoAdvanceTimer.toScreen,
    scheduledDelayMs: state.autoAdvanceTimer.delayMs,
  });
  state.autoAdvanceTimer = null;
}

function clearAnimationTimers() {
  runtimeLog("animation:timers-cleared", {
    count: state.animationTimers.length,
    queuedNodes: state.animationQueue.map((node) => animationNodeInfo(node)),
    triggerWaiterCount: Array.from(state.animationTriggerWaiters.values()).reduce((total, waiters) => total + waiters.length, 0),
  });
  for (const timer of state.animationTimers) {
    window.clearTimeout(timer);
  }
  state.animationTimers = [];
  state.animationQueue = [];
  state.animationTriggerWaiters = new Map();
  state.animationStartedNodes = new Set();
  state.animationCompletedNodes = new Set();
}

function scheduleAnimation(callback, delayMs = 0, label = "anonymous", details = {}) {
  const timerId = ++state.animationTimerSequence;
  const normalizedDelayMs = Math.max(delayMs, 0);
  runtimeLog("animation:timer-scheduled", {
    timerId,
    label,
    delayMs: normalizedDelayMs,
    pendingTimersBeforeAdd: state.animationTimers.length,
    ...details,
  });
  const timer = window.setTimeout(() => {
    runtimeLog("animation:timer-fired", {
      timerId,
      label,
      scheduledDelayMs: normalizedDelayMs,
      ...details,
    });
    callback();
  }, normalizedDelayMs);
  state.animationTimers.push(timer);
  return timer;
}

function updateAudioMute() {
  for (const element of state.audioElements.values()) {
    element.muted = state.muted;
  }
  muteButton.setAttribute("aria-pressed", String(state.muted));
  muteButton.textContent = state.muted ? "Unmute" : "Mute";
  runtimeLog("audio:mute-changed", { muted: state.muted });
}

function navigateTo(id) {
  const next = state.screens.get(id);
  if (!next) {
    runtimeLog("navigation:missing-target", {
      requestedId: id,
      knownScreenCount: state.screens.size,
    }, "warn");
    return;
  }
  clearAutoAdvanceTimer("navigation");
  runtimeLog("navigation:requested", {
    from: state.current ? { id: state.current.id, slide: state.current.slide } : null,
    to: { id: next.id, slide: next.slide },
    targetHotspotCount: (next.hotspots || []).length,
  });
  state.current = next;
  renderScreen(next);
}

async function loadAnimations(manifest) {
  const animationStatus = manifest.animationStatus;
  if (!animationStatus || animationStatus.status !== "available" || !animationStatus.path) {
    runtimeLog("animation:manifest-unavailable", { animationStatus });
    return null;
  }
  runtimeLog("animation:manifest-request", { path: animationStatus.path });
  const response = await fetch(assetUrl(animationStatus.path), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Animation manifest load failed: ${response.status}`);
  }
  const animations = await response.json();
  runtimeLog("animation:manifest-loaded", {
    path: animationStatus.path,
    slideCount: (animations.slides || []).length,
    summary: animations.summary || null,
  });
  return animations;
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
  runtimeLog("input:hotspot-action", {
    hotspotId: hotspot.id,
    action: hotspot.action,
    shapeId: hotspot.shapeId,
    targetSlide: hotspot.targetSlide,
    targetId: hotspot.targetSlide ? screenId(hotspot.targetSlide) : null,
    mediaBindingId: hotspot.mediaBindingId || null,
    label: hotspot.label || null,
  });
  unlockAudio();
  if (hotspot.action === "hyperlink" && hotspot.targetSlide) {
    navigateTo(screenId(hotspot.targetSlide));
    return;
  }
  if (hotspot.action === "media") {
    const binding = mediaBindingForHotspot(hotspot);
    runtimeLog("audio:media-hotspot-binding", { hotspotId: hotspot.id, binding });
    if (binding && binding.status === "mapped" && binding.audioSource) {
      playAudioSource(binding.audioSource, binding.startSeconds || 0, binding.cueBehavior || {});
    } else {
      runtimeLog("audio:media-hotspot-unhandled", { hotspotId: hotspot.id, binding }, "warn");
    }
  }
}

function renderHotspots(screen) {
  hotspotsLayer.replaceChildren();
  let renderedCount = 0;
  const skipped = [];
  for (const hotspot of screen.hotspots || []) {
    if (!hotspot.bounds || !hotspot.clickable) {
      skipped.push({ id: hotspot.id, reason: !hotspot.bounds ? "missing-bounds" : "not-clickable" });
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
    renderedCount += 1;
  }
  runtimeLog("render:hotspots", {
    screen: { id: screen.id, slide: screen.slide },
    declaredCount: (screen.hotspots || []).length,
    renderedCount,
    skipped,
  });
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
  const typeCounts = {};
  const animatedShapeIds = [];
  for (const layer of layers) {
    const element = document.createElement("div");
    positionLayerElement(element, layer);
    if (layer.type === "image" && layer.instancePath) {
      const image = document.createElement("img");
      image.className = "layer-image";
      image.src = assetUrl(layer.instancePath);
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
    typeCounts[layer.type] = (typeCounts[layer.type] || 0) + 1;
    if (layer.animated) {
      animatedShapeIds.push(layer.shapeId);
    }
  }
  runtimeLog("render:layers", {
    screen: { id: screen.id, slide: screen.slide },
    layerCount: layers.length,
    typeCounts,
    animatedLayerCount: animatedShapeIds.length,
    animatedShapeIds,
  });
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
    runtimeLog("animation:trigger-wait-registered", {
      node: animationNodeInfo(node),
      key,
      waiterCountForKey: waiters.length,
    });
  }
}

function emitAnimationTrigger(triggerEvent, node) {
  const localId = nodeLocalId(node);
  if (!localId) {
    runtimeLog("animation:trigger-not-emitted", {
      triggerEvent,
      node: animationNodeInfo(node),
      reason: "node has no local id",
    }, "warn");
    return;
  }
  const key = triggerKey(triggerEvent, localId);
  const waiters = state.animationTriggerWaiters.get(key);
  if (!waiters || waiters.length === 0) {
    runtimeLog("animation:trigger-emitted", {
      triggerEvent,
      key,
      node: animationNodeInfo(node),
      waiterCount: 0,
    });
    return;
  }
  state.animationTriggerWaiters.delete(key);
  runtimeLog("animation:trigger-emitted", {
    triggerEvent,
    key,
    node: animationNodeInfo(node),
    waiterCount: waiters.length,
    waiters: waiters.map((waiter) => ({ node: animationNodeInfo(waiter.node), delayMs: waiter.delayMs })),
  });
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

function animationElementInfo(element) {
  if (!element) {
    return null;
  }
  return {
    layerId: element.dataset.layerId,
    shapeId: element.dataset.shapeId,
    animated: element.dataset.animated === "true",
    metrics: {
      x: Number.parseFloat(element.dataset.pptX || "0"),
      y: Number.parseFloat(element.dataset.pptY || "0"),
      width: Number.parseFloat(element.dataset.pptW || "0"),
      height: Number.parseFloat(element.dataset.pptH || "0"),
    },
    style: {
      visibility: element.style.visibility || "",
      opacity: element.style.opacity || "",
      transform: element.style.transform || "",
      transition: element.style.transition || "",
    },
  };
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
    runtimeLog("animation:set-skipped", { strings, reason: "style.visibility not present" });
    return;
  }
  const visibility = strings.includes("hidden") ? "hidden" : strings.includes("visible") ? "visible" : null;
  if (!visibility) {
    runtimeLog("animation:set-skipped", { strings, reason: "visibility value not recognized" }, "warn");
    return;
  }
  runtimeLog("animation:set", { visibility, targetCount: elements.length, targets: elements.map(animationElementInfo) });
  for (const element of elements) {
    element.style.visibility = visibility;
    if (visibility === "visible") {
      element.style.opacity = element.style.opacity || "1";
    }
  }
}

function applyEffectBehavior(elements, strings, timing) {
  if (!strings.some((value) => value === "fade" || value === "dissolve")) {
    runtimeLog("animation:effect-skipped", { strings, reason: "fade/dissolve not present" });
    return;
  }
  runtimeLog("animation:effect", {
    effect: strings.find((value) => value === "fade" || value === "dissolve"),
    timing,
    targetCount: elements.length,
    targets: elements.map(animationElementInfo),
  });
  for (const element of elements) {
    const originalOpacity = element.style.opacity;
    const originalVisibility = element.style.visibility;
    element.style.visibility = "visible";
    element.style.opacity = "0";
    element.style.transition = transitionList(["opacity"], timing);
    window.requestAnimationFrame(() => {
      runtimeLog("animation:effect-frame", { effect: "opacity", target: animationElementInfo(element) });
      element.style.opacity = "1";
    });
    if (timing.autoReverse) {
      scheduleAnimation(() => {
        runtimeLog("animation:effect-autoreverse", { target: animationElementInfo(element) });
        element.style.opacity = "0";
      }, timing.duration, "effect-auto-reverse", { target: animationElementInfo(element) });
    } else if (!timing.holdFill) {
      scheduleAnimation(() => {
        runtimeLog("animation:effect-fill-reset", { target: animationElementInfo(element) });
        element.style.opacity = originalOpacity;
        element.style.visibility = originalVisibility;
      }, timing.duration, "effect-fill-reset", { target: animationElementInfo(element) });
    }
  }
}

function applyAnimateBehavior(elements, strings, timing) {
  const property = propertyNameFromStrings(strings);
  if (!property) {
    runtimeLog("animation:animate-skipped", { strings, reason: "no ppt_x/ppt_y/ppt_w/ppt_h property" }, "warn");
    return;
  }
  const formulas = formulaStrings(strings, property);
  const targetFormula = formulas[formulas.length - 1];
  runtimeLog("animation:animate", {
    property,
    formulas,
    targetFormula,
    timing,
    targetCount: elements.length,
    targets: elements.map(animationElementInfo),
  });
  for (const element of elements) {
    const target = evaluatePowerPointFormula(targetFormula, element);
    if (target === null) {
      runtimeLog("animation:animate-target-invalid", {
        property,
        targetFormula,
        target: animationElementInfo(element),
      }, "warn");
      continue;
    }
    const original = metricFor(element, property);
    runtimeLog("animation:animate-target", {
      property,
      original,
      targetValue: target,
      targetFormula,
      element: animationElementInfo(element),
    });
    element.style.transition =
      property === "ppt_x" || property === "ppt_y"
        ? transitionList(["left", "top"], timing)
        : transitionList(["width", "height"], timing);
    window.requestAnimationFrame(() => {
      setMetric(element, property, target);
    });
    if (timing.autoReverse) {
      scheduleAnimation(() => {
        runtimeLog("animation:property-autoreverse", { property, value: original, target: animationElementInfo(element) });
        setMetric(element, property, original);
      }, timing.duration, "property-auto-reverse", { property, target: animationElementInfo(element) });
    } else if (!timing.holdFill) {
      scheduleAnimation(() => {
        runtimeLog("animation:property-fill-reset", { property, value: original, target: animationElementInfo(element) });
        setMetric(element, property, original);
      }, timing.duration, "property-fill-reset", { property, target: animationElementInfo(element) });
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
    runtimeLog("animation:motion-skipped", { path, strings, reason: "no valid motion endpoint" }, "warn");
    return;
  }
  runtimeLog("animation:motion", {
    path,
    endpoint,
    timing,
    targetCount: elements.length,
    targets: elements.map(animationElementInfo),
  });
  for (const element of elements) {
    const originalTransform = element.style.transform;
    element.style.transition = transitionList(["transform"], timing);
    window.requestAnimationFrame(() => {
      const baseTransform = element.dataset.baseTransform || "";
      runtimeLog("animation:motion-frame", {
        endpoint,
        baseTransform,
        target: animationElementInfo(element),
      });
      element.style.transform = `${baseTransform} translate(${endpoint.x * 100}cqw, ${endpoint.y * 100}cqh)`.trim();
    });
    if (timing.autoReverse) {
      scheduleAnimation(() => {
        runtimeLog("animation:motion-autoreverse", { target: animationElementInfo(element) });
        element.style.transform = originalTransform;
      }, timing.duration, "motion-auto-reverse", { target: animationElementInfo(element) });
    } else if (!timing.holdFill) {
      scheduleAnimation(() => {
        runtimeLog("animation:motion-fill-reset", { target: animationElementInfo(element) });
        element.style.transform = originalTransform;
      }, timing.duration, "motion-fill-reset", { target: animationElementInfo(element) });
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
  const fromX = littleEndianFloatFromHex(atom.payloadHex, 12);
  const fromY = littleEndianFloatFromHex(atom.payloadHex, 16);
  const toX = littleEndianFloatFromHex(atom.payloadHex, 20);
  const toY = littleEndianFloatFromHex(atom.payloadHex, 24);
  if (![fromX, fromY, toX, toY].every(Number.isFinite)) {
    return null;
  }
  return {
    from: { x: fromX / 100, y: fromY / 100 },
    to: { x: toX / 100, y: toY / 100 },
  };
}

function applyScaleBehavior(elements, behavior, timing) {
  const scale = scaleTargetFromBehavior(behavior);
  if (!scale) {
    runtimeLog("animation:scale-skipped", { timing, reason: "scale atom missing or invalid" }, "warn");
    return;
  }
  runtimeLog("animation:scale", {
    scale,
    timing,
    targetCount: elements.length,
    targets: elements.map(animationElementInfo),
  });
  for (const element of elements) {
    const originalTransform = element.style.transform;
    const baseTransform = element.dataset.baseTransform || "";
    element.style.transition = "none";
    element.style.transform = `${baseTransform} scale(${scale.from.x}, ${scale.from.y})`.trim();
    void element.offsetWidth;
    element.style.transition = transitionList(["transform"], timing);
    window.requestAnimationFrame(() => {
      runtimeLog("animation:scale-frame", {
        scale,
        baseTransform,
        target: animationElementInfo(element),
      });
      element.style.transform = `${baseTransform} scale(${scale.to.x}, ${scale.to.y})`.trim();
    });
    if (timing.autoReverse || !timing.holdFill) {
      scheduleAnimation(() => {
        runtimeLog("animation:scale-fill-reset", { target: animationElementInfo(element) });
        element.style.transform = originalTransform;
      }, timing.duration, "scale-fill-reset", { target: animationElementInfo(element) });
    }
  }
}

function applyCommandBehavior(node, behavior, strings) {
  if (!strings.some((value) => value.startsWith("playFrom"))) {
    runtimeLog("animation:command-skipped", { node: animationNodeInfo(node), strings, reason: "playFrom command not present" });
    return;
  }
  const targets = behavior.targets && behavior.targets.length ? behavior.targets : node.targets || [];
  const startMatch = strings.find((value) => value.startsWith("playFrom"))?.match(/playFrom\\(([-+\\d.]+)\\)/);
  const startSeconds = startMatch ? Number.parseFloat(startMatch[1]) : 0;
  runtimeLog("animation:command", {
    node: animationNodeInfo(node),
    strings,
    startSeconds,
    targets: targets.map((target) => ({ kind: target.kind, shapeId: target.shapeId })),
  });
  for (const target of targets) {
    if (target.kind !== "shape") {
      continue;
    }
    const binding = state.mediaBindings.get(`${state.current.slide}:${target.shapeId}`);
    if (binding && binding.status === "mapped" && binding.audioSource) {
      playAudioSource(binding.audioSource, startSeconds, binding.cueBehavior || {});
    } else {
      runtimeLog("animation:command-audio-unhandled", {
        node: animationNodeInfo(node),
        target,
        binding: binding || null,
      }, "warn");
    }
  }
}

function applyBehavior(node, behavior) {
  const strings = parsedStrings(behavior.variants);
  const timing = nodeTiming(node);
  runtimeLog("animation:behavior", {
    node: animationNodeInfo(node),
    kind: behavior.kind,
    strings,
    timing,
    targets: (behavior.targets && behavior.targets.length ? behavior.targets : node.targets || []).map((target) => ({
      kind: target.kind,
      shapeId: target.shapeId,
    })),
  });
  if (behavior.kind === "command") {
    applyCommandBehavior(node, behavior, strings);
    return;
  }
  const elements = targetsFor(node, behavior);
  if (elements.length === 0) {
    runtimeLog("animation:behavior-no-elements", {
      node: animationNodeInfo(node),
      kind: behavior.kind,
      strings,
      declaredTargets: behavior.targets || node.targets || [],
    }, "warn");
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
  } else {
    runtimeLog("animation:behavior-unsupported", { node: animationNodeInfo(node), kind: behavior.kind }, "warn");
  }
}

function runAnimationNode(node, baseDelay = 0, allowClickNode = false, allowTriggeredNode = false, autoplay = false) {
  runtimeLog("animation:node-evaluate", {
    node: animationNodeInfo(node),
    baseDelay,
    allowClickNode,
    allowTriggeredNode,
    autoplay,
    completed: state.animationCompletedNodes.has(node.id),
  });
  if (state.animationCompletedNodes.has(node.id) && nodeRestartMode(node) === 0 && !allowTriggeredNode && !allowClickNode) {
    runtimeLog("animation:node-skipped", { node: animationNodeInfo(node), reason: "already completed and restart is disabled" });
    return;
  }
  if (nodeTriggerConditions(node).length > 0 && !allowTriggeredNode) {
    registerAnimationTriggerWaits(node);
    runtimeLog("animation:node-waiting", { node: animationNodeInfo(node), reason: "start/end trigger condition" });
    return;
  }
  if (nodeWaitsForClick(node) && !allowClickNode && !autoplay) {
    state.animationQueue.push(node);
    runtimeLog("animation:node-queued", {
      node: animationNodeInfo(node),
      reason: "OnNext/OnPrev click condition",
      queueLength: state.animationQueue.length,
    });
    return;
  }
  const startDelay = baseDelay + nodeDelay(node);
  const nodeDetails = { node: animationNodeInfo(node), startDelay, baseDelay };
  scheduleAnimation(() => {
    state.animationStartedNodes.add(node.id);
    runtimeLog("animation:node-started", {
      ...nodeDetails,
      startedCount: state.animationStartedNodes.size,
    });
    emitAnimationTrigger(3, node);
  }, startDelay, "animation-node-start", nodeDetails);
  if (node.behaviors && node.behaviors.length) {
    scheduleAnimation(() => {
      runtimeLog("animation:node-behaviors-start", {
        ...nodeDetails,
        behaviorCount: node.behaviors.length,
      });
      for (const behavior of node.behaviors) {
        applyBehavior(node, behavior);
      }
    }, startDelay, "animation-node-behaviors", nodeDetails);
  }
  scheduleAnimation(() => {
    state.animationCompletedNodes.add(node.id);
    runtimeLog("animation:node-completed", {
      ...nodeDetails,
      completedCount: state.animationCompletedNodes.size,
    });
    emitAnimationTrigger(4, node);
  }, startDelay + nodeDuration(node), "animation-node-complete", nodeDetails);
  runtimeLog("animation:node-scheduled", {
    ...nodeDetails,
    durationMs: nodeDuration(node),
    behaviorCount: (node.behaviors || []).length,
    childCount: (node.children || []).length,
  });
  scheduleChildNodes(node, startDelay, autoplay);
}

function scheduleChildNodes(node, startDelay, autoplay = false) {
  const children = node.children || [];
  if (!children.length) {
    runtimeLog("animation:children-none", { node: animationNodeInfo(node) });
    return;
  }
  if (nodeChildrenRunOnClick(node) && !autoplay) {
    for (const child of children) {
      state.animationQueue.push(child);
    }
    runtimeLog("animation:children-queued", {
      node: animationNodeInfo(node),
      reason: "sequence waits for click",
      childCount: children.length,
      queueLength: state.animationQueue.length,
      children: children.map((child) => animationNodeInfo(child)),
    });
    return;
  }
  if (nodeRunsSequentialChildren(node)) {
    let childDelay = 0;
    for (const child of children) {
      runtimeLog("animation:child-scheduled", {
        parent: animationNodeInfo(node),
        child: animationNodeInfo(child),
        mode: "sequential",
        startDelay: startDelay + childDelay,
      });
      runAnimationNode(child, startDelay + childDelay, false, false, autoplay);
      childDelay += subtreeDuration(child);
    }
    return;
  }
  for (const child of children) {
    runtimeLog("animation:child-scheduled", {
      parent: animationNodeInfo(node),
      child: animationNodeInfo(child),
      mode: "parallel",
      startDelay,
    });
    runAnimationNode(child, startDelay, false, false, autoplay);
  }
}

function setupAnimations(screen) {
  const autoplay = screen.slide === 1;
  runtimeLog("animation:setup-start", {
    screen: { id: screen.id, slide: screen.slide },
    layerElementCount: state.currentLayerElements.size,
    loadedAnimationSlide: state.animationSlides.has(screen.slide),
    autoplay,
  });
  clearAnimationTimers();
  for (const element of state.currentLayerElements.values()) {
    element.style.visibility = "";
    element.style.opacity = "";
    element.style.transition = "";
    element.style.transform = element.dataset.baseTransform || "";
  }
  const slideAnimations = state.animationSlides.get(screen.slide);
  if (!slideAnimations) {
    runtimeLog("animation:setup-none", {
      screen: { id: screen.id, slide: screen.slide },
      reason: state.animations ? "slide has no animation entry" : "animation manifest not loaded",
    });
    return;
  }
  runtimeLog("animation:setup-roots", {
    screen: { id: screen.id, slide: screen.slide },
    rootCount: (slideAnimations.rootTimeNodes || []).length,
    roots: (slideAnimations.rootTimeNodes || []).map((node) => animationNodeInfo(node)),
  });
  for (const node of slideAnimations.rootTimeNodes || []) {
    runAnimationNode(node, 0, false, false, autoplay);
  }
}

function advanceAnimation() {
  const node = state.animationQueue.shift();
  if (!node) {
    runtimeLog("input:animation-advance", {
      action: "advance-animation",
      result: "no queued animation node",
      queueLength: 0,
    });
    return false;
  }
  runtimeLog("input:animation-advance", {
    action: "advance-animation",
    result: "running queued animation node",
    node: animationNodeInfo(node),
    queueLengthAfterShift: state.animationQueue.length,
  });
  runAnimationNode(node, 0, true);
  return true;
}

function renderScreen(screen) {
  const slideNumber = String(screen.slide).padStart(3, "0");
  const renderedLayers = renderLayers(screen);
  runtimeLog("render:screen-start", {
    screen: { id: screen.id, slide: screen.slide },
    image: screen.image,
    renderedLayers,
    hotspotCount: (screen.hotspots || []).length,
    transition: screen.transition || null,
  });
  screenImage.alt = `Screen ${slideNumber}`;
  screenImage.src = assetUrl(screen.image);
  screenImage.hidden = renderedLayers;
  layersLayer.hidden = !renderedLayers;
  missingRender.hidden = true;
  setupAnimations(screen);
  applySlideTransition(screen);
  scheduleAutoAdvance(screen);
  renderHotspots(screen);
  setStatus(`Screen ${slideNumber}`);
  runtimeLog("render:screen-complete", {
    screen: { id: screen.id, slide: screen.slide },
    imageHidden: screenImage.hidden,
    layersHidden: layersLayer.hidden,
    queuedAnimationNodes: state.animationQueue.length,
    pendingAnimationTimers: state.animationTimers.length,
  });
}

function animationTimelineForScreen(screen) {
  const slideAnimations = state.animationSlides.get(screen.slide);
  if (!slideAnimations) {
    return {
      available: false,
      rootCount: 0,
      durationMs: 0,
    };
  }
  const roots = slideAnimations.rootTimeNodes || [];
  const durations = roots.map((node) => subtreeDuration(node)).filter(Number.isFinite);
  return {
    available: true,
    rootCount: roots.length,
    durationMs: durations.length > 0 ? Math.max(...durations) : 0,
  };
}

function scheduleAutoAdvance(screen) {
  const transition = screen.transition;
  runtimeLog("navigation:auto-advance-evaluate", {
    screen: { id: screen.id, slide: screen.slide },
    transition: transition || null,
  });
  clearAutoAdvanceTimer("rescheduled");
  if (
    !transition ||
    !(transition.flagNames || []).includes("autoAdvance") ||
    !Number.isFinite(transition.slideTimeMs) ||
    transition.slideTimeMs <= 0
  ) {
    runtimeLog("navigation:auto-advance-not-scheduled", {
      screen: { id: screen.id, slide: screen.slide },
      reason: !transition
        ? "no transition"
        : !(transition.flagNames || []).includes("autoAdvance")
          ? "autoAdvance flag missing"
          : !Number.isFinite(transition.slideTimeMs)
            ? "slideTimeMs is not finite"
            : "slideTimeMs is not positive",
    });
    return;
  }
  const nextScreen = state.screens.get(screenId(Number(screen.slide) + 1));
  if (!nextScreen) {
    runtimeLog("navigation:auto-advance-not-scheduled", {
      screen: { id: screen.id, slide: screen.slide },
      reason: "next sequential screen missing",
      requestedNextId: screenId(Number(screen.slide) + 1),
    }, "warn");
    return;
  }
  const animationTimeline = animationTimelineForScreen(screen);
  const sourceDelayMs = transition.slideTimeMs;
  const scheduledDelayMs = Math.max(sourceDelayMs, animationTimeline.durationMs);
  const timerId = ++state.autoAdvanceSequence;
  const fromScreen = { id: screen.id, slide: screen.slide };
  const toScreen = { id: nextScreen.id, slide: nextScreen.slide };
  runtimeLog("navigation:auto-advance-scheduled", {
    timerId,
    from: fromScreen,
    to: toScreen,
    sourceDelayMs,
    animationTimeline,
    scheduledDelayMs,
    sourceRecordOffset: transition.recordOffset ?? null,
    sourceRawHex: transition.rawHex ?? null,
    reason: animationTimeline.durationMs > sourceDelayMs
      ? "wait for the longer of PowerPoint slide time and decoded animation timeline"
      : "PowerPoint autoAdvance slide time; animation timeline completes before it",
  });
  const timerRecord = {
    id: timerId,
    handle: null,
    fromScreen,
    toScreen,
    delayMs: scheduledDelayMs,
  };
  timerRecord.handle = window.setTimeout(() => {
    if (state.autoAdvanceTimer !== timerRecord) {
      runtimeLog("navigation:auto-advance-stale", {
        timerId,
        from: fromScreen,
        to: toScreen,
        reason: "timer was replaced or cleared",
      }, "warn");
      return;
    }
    state.autoAdvanceTimer = null;
    runtimeLog("navigation:auto-advance-fired", {
      timerId,
      from: fromScreen,
      to: toScreen,
      sourceDelayMs,
      animationTimeline,
      scheduledDelayMs,
    });
    navigateTo(nextScreen.id);
  }, scheduledDelayMs);
  state.autoAdvanceTimer = timerRecord;
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
  const removedClasses = [];
  for (const className of Array.from(stage.classList)) {
    if (className.startsWith("transition-effect-") || className.startsWith("transition-direction-")) {
      stage.classList.remove(className);
      removedClasses.push(className);
    }
  }
  if (removedClasses.length > 0) {
    runtimeLog("transition:classes-cleared", { removedClasses });
  }
}

function applySlideTransition(screen) {
  const transition = screen.transition;
  if (!transition || transition.effectType === 0) {
    runtimeLog("transition:not-applied", {
      screen: { id: screen.id, slide: screen.slide },
      transition: transition || null,
      reason: !transition ? "no transition" : "effectType is zero",
    });
    clearSlideTransitionClasses();
    return;
  }
  const durationMs = transitionDuration(screen);
  const effectClass = transitionEffectClass(transition);
  const directionClass = transitionDirectionClass(transition);
  runtimeLog("transition:apply", {
    screen: { id: screen.id, slide: screen.slide },
    effectType: transition.effectType,
    effectDirection: transition.effectDirection,
    effectClass,
    directionClass,
    durationMs,
    transition,
  });
  stage.style.setProperty("--transition-duration", `${durationMs}ms`);
  clearSlideTransitionClasses();
  stage.classList.add(effectClass, directionClass);
  stage.classList.remove("is-transitioning");
  void stage.offsetWidth;
  stage.classList.add("is-transitioning");
  runtimeLog("transition:started", {
    screen: { id: screen.id, slide: screen.slide },
    classList: Array.from(stage.classList),
  });
  scheduleAnimation(() => {
    stage.classList.remove("is-transitioning");
    clearSlideTransitionClasses();
    runtimeLog("transition:completed", { screen: { id: screen.id, slide: screen.slide } });
  }, durationMs, "slide-transition-cleanup", {
    screen: { id: screen.id, slide: screen.slide },
    effectType: transition.effectType,
    effectDirection: transition.effectDirection,
  });
}

screenImage.addEventListener("error", () => {
  runtimeLog("render:image-error", {
    src: screenImage.src,
    currentScreen: state.current ? { id: state.current.id, slide: state.current.slide } : null,
  }, "error");
  screenImage.hidden = true;
  missingRender.hidden = false;
});

screenImage.addEventListener("load", () => {
  runtimeLog("render:image-loaded", {
    src: screenImage.src,
    naturalWidth: screenImage.naturalWidth,
    naturalHeight: screenImage.naturalHeight,
    currentScreen: state.current ? { id: state.current.id, slide: state.current.slide } : null,
  });
});

window.addEventListener("error", (event) => {
  runtimeLog("runtime:uncaught-error", {
    message: event.message,
    filename: event.filename || null,
    line: event.lineno || null,
    column: event.colno || null,
    stack: event.error?.stack || null,
  }, "error");
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  runtimeLog("runtime:unhandled-rejection", {
    message: reason instanceof Error ? reason.message : String(reason),
    stack: reason instanceof Error ? reason.stack || null : null,
  }, "error");
});

stage.addEventListener("click", () => {
  runtimeLog("input:stage-click", {
    action: "unlock-audio-and-advance",
    queueLengthBefore: state.animationQueue.length,
  });
  unlockAudio();
  advanceAnimation();
});

restartButton.addEventListener("click", () => {
  runtimeLog("input:restart", { startScreen: state.manifest?.startScreen || null });
  unlockAudio();
  stopAudio();
  navigateTo(state.manifest.startScreen);
});

muteButton.addEventListener("click", () => {
  state.muted = !state.muted;
  runtimeLog("input:mute-toggle", { muted: state.muted });
  updateAudioMute();
});

runtimeLog("manifest:request", { path: "game-manifest.json" });
fetch(assetUrl("game-manifest.json"), { cache: "no-store" })
  .then((response) => {
    if (!response.ok) {
      throw new Error(`Manifest load failed: ${response.status}`);
    }
    runtimeLog("manifest:response", { status: response.status, url: response.url });
    return response.json();
  })
  .then((manifest) => {
    state.manifest = manifest;
    state.screens = new Map(manifest.screens.map((screen) => [screen.id, screen]));
    state.mediaBindings = new Map((manifest.mediaBindings || []).map((binding) => [`${binding.slide}:${binding.shapeId}`, binding]));
    runtimeLog("manifest:loaded", {
      format: manifest.format || null,
      startScreen: manifest.startScreen,
      screenCount: state.screens.size,
      mediaBindingCount: state.mediaBindings.size,
      audioEntryCount: (manifest.audio || []).length,
      animationStatus: manifest.animationStatus || null,
      transitionStatus: manifest.transitionStatus || null,
      layerStatus: manifest.layerStatus || null,
    });
    prepareAudio();
    updateAudioMute();
    navigateTo(manifest.startScreen);
    return loadAnimations(manifest)
      .then((animations) => {
        state.animations = animations;
        state.animationSlides = new Map((animations?.slides || []).map((slide) => [slide.slide, slide]));
        runtimeLog("animation:runtime-ready", {
          slideCount: state.animationSlides.size,
          currentScreen: state.current ? { id: state.current.id, slide: state.current.slide } : null,
        });
        if (state.current) {
          setupAnimations(state.current);
          scheduleAutoAdvance(state.current);
        }
      })
      .catch((error) => {
        runtimeLog("animation:manifest-error", { message: error.message, stack: error.stack || null }, "error");
        console.warn(error);
      });
  })
  .catch((error) => {
    runtimeLog("manifest:error", { message: error.message, stack: error.stack || null }, "error");
    setStatus(error.message);
    missingRender.hidden = false;
  });
