"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.isWebKit = exports.isSafari = exports.isMac = exports.isJSDOM = exports.isIOS = exports.isFirefox = exports.isEdge = exports.isAndroid = void 0;
const hasNavigator = typeof navigator !== 'undefined';
const nav = getNavigatorData();
const platform = getPlatform();
const userAgent = getUserAgent();
const isWebKit = exports.isWebKit = typeof CSS === 'undefined' || !CSS.supports ? false : CSS.supports('-webkit-backdrop-filter:none');
const isIOS = exports.isIOS =
// iPads can claim to be MacIntel
nav.platform === 'MacIntel' && nav.maxTouchPoints > 1 ? true : /iP(hone|ad|od)|iOS/.test(nav.platform);
const isFirefox = exports.isFirefox = hasNavigator && /firefox/i.test(userAgent);
const isSafari = exports.isSafari = hasNavigator && /apple/i.test(navigator.vendor);
const isEdge = exports.isEdge = hasNavigator && /Edg/i.test(userAgent);
const isAndroid = exports.isAndroid = hasNavigator && /android/i.test(platform) || /android/i.test(userAgent);
const isMac = exports.isMac = hasNavigator && platform.toLowerCase().startsWith('mac') && !navigator.maxTouchPoints;
const isJSDOM = exports.isJSDOM = userAgent.includes('jsdom/');

// Avoid Chrome DevTools blue warning.
function getNavigatorData() {
  if (!hasNavigator) {
    return {
      platform: '',
      maxTouchPoints: -1
    };
  }
  const uaData = navigator.userAgentData;
  if (uaData?.platform) {
    return {
      platform: uaData.platform,
      maxTouchPoints: navigator.maxTouchPoints
    };
  }
  return {
    platform: navigator.platform ?? '',
    maxTouchPoints: navigator.maxTouchPoints ?? -1
  };
}
function getUserAgent() {
  if (!hasNavigator) {
    return '';
  }
  const uaData = navigator.userAgentData;
  if (uaData && Array.isArray(uaData.brands)) {
    return uaData.brands.map(({
      brand,
      version
    }) => `${brand}/${version}`).join(' ');
  }
  return navigator.userAgent;
}
function getPlatform() {
  if (!hasNavigator) {
    return '';
  }
  const uaData = navigator.userAgentData;
  if (uaData?.platform) {
    return uaData.platform;
  }
  return navigator.platform ?? '';
}