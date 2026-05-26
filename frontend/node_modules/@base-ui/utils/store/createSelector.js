"use strict";

var _interopRequireDefault = require("@babel/runtime/helpers/interopRequireDefault").default;
Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.createSelectorMemoized = exports.createSelector = void 0;
var _formatErrorMessage2 = _interopRequireDefault(require("../formatErrorMessage.js"));
var _reselect = require("reselect");
/* eslint-disable no-underscore-dangle */ // __cacheKey__

const reselectCreateSelector = (0, _reselect.createSelectorCreator)({
  memoize: _reselect.lruMemoize,
  memoizeOptions: {
    maxSize: 1,
    equalityCheck: Object.is
  }
});
/**
 * Creates a selector function that can be used to derive values from the store's state.
 * The selector can take up to three additional arguments that can be used in the selector logic.
 * This function accepts up to six functions and combines them into a single selector function.
 * The last parameter is the combiner function that combines the results of the previous selectors.
 *
 * @example
 * const selector = createSelector(
 *  (state) => state.disabled
 * );
 *
 * @example
 * const selector = createSelector(
 *   (state) => state.disabled,
 *   (state) => state.open,
 *   (disabled, open) => ({ disabled, open })
 * );
 *
 */
/* eslint-disable id-denylist */
const createSelector = (a, b, c, d, e, f, ...other) => {
  if (other.length > 0) {
    throw new Error(process.env.NODE_ENV !== "production" ? 'Unsupported number of selectors' : (0, _formatErrorMessage2.default)(1));
  }
  let selector;
  if (a && b && c && d && e && f) {
    selector = (state, a1, a2, a3) => {
      const va = a(state, a1, a2, a3);
      const vb = b(state, a1, a2, a3);
      const vc = c(state, a1, a2, a3);
      const vd = d(state, a1, a2, a3);
      const ve = e(state, a1, a2, a3);
      return f(va, vb, vc, vd, ve, a1, a2, a3);
    };
  } else if (a && b && c && d && e) {
    selector = (state, a1, a2, a3) => {
      const va = a(state, a1, a2, a3);
      const vb = b(state, a1, a2, a3);
      const vc = c(state, a1, a2, a3);
      const vd = d(state, a1, a2, a3);
      return e(va, vb, vc, vd, a1, a2, a3);
    };
  } else if (a && b && c && d) {
    selector = (state, a1, a2, a3) => {
      const va = a(state, a1, a2, a3);
      const vb = b(state, a1, a2, a3);
      const vc = c(state, a1, a2, a3);
      return d(va, vb, vc, a1, a2, a3);
    };
  } else if (a && b && c) {
    selector = (state, a1, a2, a3) => {
      const va = a(state, a1, a2, a3);
      const vb = b(state, a1, a2, a3);
      return c(va, vb, a1, a2, a3);
    };
  } else if (a && b) {
    selector = (state, a1, a2, a3) => {
      const va = a(state, a1, a2, a3);
      return b(va, a1, a2, a3);
    };
  } else if (a) {
    selector = a;
  } else {
    throw /* minify-error-disabled */new Error('Missing arguments');
  }
  return selector;
};
/* eslint-enable id-denylist */
exports.createSelector = createSelector;
const createSelectorMemoized = (...selectors) => {
  const cache = new WeakMap();
  let nextCacheId = 1;
  const combiner = selectors[selectors.length - 1];
  const nSelectors = selectors.length - 1 || 1;
  // (s1, s2, ..., sN, a1, a2, a3) => { ... }
  const argsLength = combiner.length - nSelectors;
  if (argsLength > 3) {
    throw new Error(process.env.NODE_ENV !== "production" ? 'Unsupported number of arguments' : (0, _formatErrorMessage2.default)(2));
  }
  const selector = (state, a1, a2, a3) => {
    let cacheKey = state.__cacheKey__;
    if (!cacheKey) {
      cacheKey = {
        id: nextCacheId
      };
      state.__cacheKey__ = cacheKey;
      nextCacheId += 1;
    }
    let fn = cache.get(cacheKey);
    if (!fn) {
      let reselectArgs = selectors;
      const selectorArgs = [undefined, undefined, undefined];
      switch (argsLength) {
        case 0:
          break;
        case 1:
          {
            reselectArgs = [...selectors.slice(0, -1), () => selectorArgs[0], combiner];
            break;
          }
        case 2:
          {
            reselectArgs = [...selectors.slice(0, -1), () => selectorArgs[0], () => selectorArgs[1], combiner];
            break;
          }
        case 3:
          {
            reselectArgs = [...selectors.slice(0, -1), () => selectorArgs[0], () => selectorArgs[1], () => selectorArgs[2], combiner];
            break;
          }
        default:
          throw new Error(process.env.NODE_ENV !== "production" ? 'Unsupported number of arguments' : (0, _formatErrorMessage2.default)(2));
      }
      fn = reselectCreateSelector(...reselectArgs);
      fn.selectorArgs = selectorArgs;
      cache.set(cacheKey, fn);
    }
    fn.selectorArgs[0] = a1;
    fn.selectorArgs[1] = a2;
    fn.selectorArgs[2] = a3;

    // prettier-ignore
    switch (argsLength) {
      case 0:
        return fn(state);
      case 1:
        return fn(state, a1);
      case 2:
        return fn(state, a1, a2);
      case 3:
        return fn(state, a1, a2, a3);
      default:
        throw /* minify-error-disabled */new Error('unreachable');
    }
  };
  return selector;
};
exports.createSelectorMemoized = createSelectorMemoized;