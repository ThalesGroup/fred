import styles from "./ImageFileInput.module.scss";
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
    <label className={styles["image-file-input-container"]}>
      <input type="file" ref={ref} className={styles["native-input"]} {...props} />
      <div
        className={styles["image-wrapper"]}
        style={
          {
            "--image-width": width,
            "--image-height": height,
          } as CSSProperties
        }
      >
        <img className={styles["image-file-input-image"]} src={imageUrl} alt={alt} />
      </div>
    </label>
  );
}
