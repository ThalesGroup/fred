import styles from "./ImageFileInput.module.scss";
import React, { forwardRef, InputHTMLAttributes } from "react";

interface ImageFileInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  imageUrl?: string;
  width?: string;
  height?: string;
  alt: string;
  accept: string;
}

const ImageFileInput = forwardRef<HTMLInputElement, ImageFileInputProps>(
  ({ imageUrl, width, height, alt, ...props }, ref) => {
    return (
      <label className={styles["image-file-input-container"]}>
        <input type="file" ref={ref} className={styles["native-input"]} {...props} />
        <div
          className={styles["image-wrapper"]}
          style={
            {
              "--image-width": width,
              "--image-height": height,
            } as React.CSSProperties
          }
        >
          <img className={styles["image-file-input-image"]} src={imageUrl} alt={alt} />
        </div>
      </label>
    );
  },
);

ImageFileInput.displayName = "ImageFileInput";

export default ImageFileInput;
