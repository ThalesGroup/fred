"use strict";

var _interopRequireWildcard = require("@babel/runtime/helpers/interopRequireWildcard").default;
Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.SafeReact = void 0;
var React = _interopRequireWildcard(require("react"));
// https://github.com/mui/material-ui/issues/41190#issuecomment-2040873379
const SafeReact = exports.SafeReact = {
  ...React
};