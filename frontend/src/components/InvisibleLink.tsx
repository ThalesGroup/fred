import { Link, LinkProps } from "react-router-dom";

// Wrapper arround react-router Link that doesn't apply default
// link styles (color, underline, etc.)
function InvisibleLink(props: LinkProps) {
  return (
    <Link
      {...props}
      style={{
        textDecoration: "none",
        color: "inherit",
        ...(props.style || {}),
      }}
    >
      {props.children}
    </Link>
  );
}

export default InvisibleLink;
