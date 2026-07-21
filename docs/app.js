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

function playAudioSource(source, startSeconds = 0) {
  const element = state.audioElements.get(source);
  if (!element) {
    return;
  }
  if (!state.audioUnlocked) {
    state.pendingAudioCommands.push({ source, startSeconds });
    return;
  }
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
    playAudioSource(command.source, command.startSeconds);
  }
}

function clearAnimationTimers() {
  for (const timer of state.animationTimers) {
    window.clearTimeout(timer);
  }
  state.animationTimers = [];
  state.animationQueue = [];
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

function renderHotspots(screen) {
  hotspotsLayer.replaceChildren();
  for (const hotspot of screen.hotspots || []) {
    if (!hotspot.bounds || !hotspot.enabled || !hotspot.targetSlide) {
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
    button.dataset.target = screenId(hotspot.targetSlide);
    button.setAttribute("aria-label", hotspot.label || `Go to slide ${hotspot.targetSlide}`);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      unlockAudio();
      navigateTo(event.currentTarget.dataset.target);
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
      element.style.fontSize = `${Math.max(layer.bounds.height * 72, 1)}cqh`;
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
    if (parsed && Number.isFinite(parsed.delayMs) && parsed.delayMs > delay) {
      delay = parsed.delayMs;
    }
  }
  return delay;
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
  const parsed = node.timeNode && node.timeNode.parsed;
  if (!parsed || !Number.isFinite(parsed.durationMs) || parsed.durationMs <= 1) {
    return 1;
  }
  return parsed.durationMs;
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

function applyEffectBehavior(elements, strings, duration) {
  if (!strings.some((value) => value === "fade" || value === "dissolve")) {
    return;
  }
  for (const element of elements) {
    element.style.visibility = "visible";
    element.style.opacity = "0";
    element.style.transition = `opacity ${duration}ms linear`;
    window.requestAnimationFrame(() => {
      element.style.opacity = "1";
    });
  }
}

function applyAnimateBehavior(elements, strings, duration) {
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
    element.style.transition =
      property === "ppt_x" || property === "ppt_y"
        ? `left ${duration}ms linear, top ${duration}ms linear`
        : `width ${duration}ms linear, height ${duration}ms linear`;
    window.requestAnimationFrame(() => {
      setMetric(element, property, target);
    });
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

function applyMotionBehavior(elements, strings, duration) {
  const path = strings.find((value) => value.startsWith("M "));
  const endpoint = motionEndpoint(path);
  if (!endpoint) {
    return;
  }
  for (const element of elements) {
    element.style.transition = `transform ${duration}ms linear`;
    window.requestAnimationFrame(() => {
      element.style.transform = `translate(${endpoint.x * 100}cqw, ${endpoint.y * 100}cqh)`;
    });
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
      playAudioSource(binding.audioSource, startSeconds);
    }
  }
}

function applyBehavior(node, behavior) {
  const strings = parsedStrings(behavior.variants);
  const duration = nodeDuration(node);
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
    applyEffectBehavior(elements, strings, duration);
  } else if (behavior.kind === "animate") {
    applyAnimateBehavior(elements, strings, duration);
  } else if (behavior.kind === "motion") {
    applyMotionBehavior(elements, strings, duration);
  }
}

function runAnimationNode(node, baseDelay = 0, allowClickNode = false) {
  if (nodeWaitsForClick(node) && !allowClickNode) {
    state.animationQueue.push(node);
    return;
  }
  const startDelay = baseDelay + nodeDelay(node);
  if (node.behaviors && node.behaviors.length) {
    scheduleAnimation(() => {
      for (const behavior of node.behaviors) {
        applyBehavior(node, behavior);
      }
    }, startDelay);
  }
  for (const child of node.children || []) {
    runAnimationNode(child, startDelay, false);
  }
}

function setupAnimations(screen) {
  clearAnimationTimers();
  for (const element of state.currentLayerElements.values()) {
    element.style.visibility = "";
    element.style.opacity = "";
    element.style.transition = "";
    element.style.transform = "";
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

function applySlideTransition(screen) {
  const transition = screen.transition;
  if (!transition || transition.effectType === 0) {
    return;
  }
  stage.style.setProperty("--transition-duration", `${transitionDuration(screen)}ms`);
  stage.classList.remove("is-transitioning");
  void stage.offsetWidth;
  stage.classList.add("is-transitioning");
  scheduleAnimation(() => {
    stage.classList.remove("is-transitioning");
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
