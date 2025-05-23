// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.


/**
 * Module declaration for importing SVG files as React components.
 * 
 * This module allows TypeScript to understand and type-check SVG imports,
 * treating them as React functional components with SVG properties.
 * 
 * @module "*.svg"
 * @requires react
 * 
 * @typedef {React.FC<React.SVGProps<SVGSVGElement>>} content - The React component representing the SVG.
 * 
 * @example
 * import Logo from './logo.svg';
 * 
 * const App = () => (
 *   <div>
 *     <Logo width={50} height={50} />
 *   </div>
 * );
 */
declare module "*.svg" {
    import React = require("react");
    const content: React.FC<React.SVGProps<SVGSVGElement>>;
    export default content;
}