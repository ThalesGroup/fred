// src/types/svg.d.ts
declare module "*.svg" {
  import * as React from "react";
  export const ReactComponent: React.FunctionComponent<
    React.SVGProps<SVGSVGElement> & { title?: string }
  >;
  const src: string; // default is still available as URL if you ever need it
  export default src;
}
