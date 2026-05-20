import styles from "./ImageFileInput.module.css";
import { ComponentPropsWithRef, CSSProperties } from "react";

interface ImageFileInputProps extends Omit<ComponentPropsWithRef<"input">, "type"> {
  imageUrl?: string;
  width?: string;
  height?: string;
  alt: string;
  accept: string;
}
export default function ImageFileInput({ imageUrl, width, height, alt, ref, ...props }: ImageFileInputProps) {
  return (
    <label className={styles.imageFileInputContainer}>
      <input type="file" ref={ref} className={styles.nativeInput} {...props} />
      <div
        className={styles.imageWrapper}
        style={
          {
            "--image-width": width,
            "--image-height": height,
          } as CSSProperties
        }
      >
        <img className={styles.imageFileInputImage} src={imageUrl} alt={alt} />
      </div>
    </label>
  );
}
