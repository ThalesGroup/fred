
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