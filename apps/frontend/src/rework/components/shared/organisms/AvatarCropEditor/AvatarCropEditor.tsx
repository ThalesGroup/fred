// Copyright Thales 2026
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

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./AvatarCropEditor.module.scss";

// Display size of the square crop viewport, and the exported avatar size. The
// export is bounded (512×512 WebP) so a huge source image never reaches the
// avatar surfaces at full resolution (#2300).
const VIEWPORT = 288;
const OUTPUT = 512;
const MIN_ZOOM = 1;
const MAX_ZOOM = 3;

interface AvatarCropEditorProps {
  /** The image the user picked; its object URL drives the editor. */
  file: File;
  open: boolean;
  onCancel: () => void;
  /** Receives the cropped square as a bounded WebP blob. */
  onSave: (blob: Blob) => void | Promise<void>;
  /** Disables the confirm button while the upload is in flight. */
  saving?: boolean;
}

/**
 * Square avatar crop editor (#2300): the picked image fills a 1:1 viewport that
 * the user pans (drag) and zooms (slider or wheel); the visible square is
 * exported as a bounded WebP. Rendered in the app's central `Dialog`. Custom
 * canvas implementation — no external cropper dependency.
 */
export default function AvatarCropEditor({ file, open, onCancel, onSave, saving = false }: AvatarCropEditorProps) {
  const { t } = useTranslation();
  const imgRef = useRef<HTMLImageElement>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef<{ px: number; py: number; ox: number; oy: number } | null>(null);

  // One object URL per picked file, revoked on change/unmount.
  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    setNatural(null);
    setZoom(MIN_ZOOM);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  // Scale that makes the image *cover* the square viewport (no empty gaps).
  const baseScale = natural ? Math.max(VIEWPORT / natural.w, VIEWPORT / natural.h) : 1;
  const bz = baseScale * zoom;
  const dispW = natural ? natural.w * bz : 0;
  const dispH = natural ? natural.h * bz : 0;

  // Keep the image covering the viewport: its top-left stays in [V - disp, 0].
  const clamp = useCallback(
    (x: number, y: number) => ({
      x: Math.min(0, Math.max(VIEWPORT - dispW, x)),
      y: Math.min(0, Math.max(VIEWPORT - dispH, y)),
    }),
    [dispW, dispH],
  );

  const handleLoad = () => {
    const el = imgRef.current;
    if (!el) return;
    const w = el.naturalWidth;
    const h = el.naturalHeight;
    setNatural({ w, h });
    const base = Math.max(VIEWPORT / w, VIEWPORT / h);
    // Centre the covered image on first load.
    setOffset({ x: (VIEWPORT - w * base) / 2, y: (VIEWPORT - h * base) / 2 });
  };

  const applyZoom = useCallback(
    (nextZoom: number) => {
      const z = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom));
      // Anchor the point under the viewport centre so zoom feels centred.
      const centerSourceX = (VIEWPORT / 2 - offset.x) / bz;
      const centerSourceY = (VIEWPORT / 2 - offset.y) / bz;
      const nbz = baseScale * z;
      const next = clamp(VIEWPORT / 2 - centerSourceX * nbz, VIEWPORT / 2 - centerSourceY * nbz);
      setZoom(z);
      setOffset(next);
    },
    [offset.x, offset.y, bz, baseScale, clamp],
  );

  const onPointerDown = (e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { px: e.clientX, py: e.clientY, ox: offset.x, oy: offset.y };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const { px, py, ox, oy } = drag.current;
    setOffset(clamp(ox + (e.clientX - px), oy + (e.clientY - py)));
  };
  const onPointerUp = (e: React.PointerEvent) => {
    drag.current = null;
    e.currentTarget.releasePointerCapture(e.pointerId);
  };
  const onWheel = (e: React.WheelEvent) => {
    applyZoom(zoom - e.deltaY * 0.0015);
  };

  const handleConfirm = async () => {
    const el = imgRef.current;
    if (!el || !natural) return;
    const canvas = document.createElement("canvas");
    canvas.width = OUTPUT;
    canvas.height = OUTPUT;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // Map the viewport's visible square back to source pixels.
    const sSize = VIEWPORT / bz;
    const sx = -offset.x / bz;
    const sy = -offset.y / bz;
    ctx.drawImage(el, sx, sy, sSize, sSize, 0, 0, OUTPUT, OUTPUT);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob((b) => resolve(b), "image/webp", 0.9));
    if (blob) await onSave(blob);
  };

  return (
    <Dialog
      open={open}
      title={t("rework.avatarCrop.title")}
      confirmLabel={t("rework.avatarCrop.save")}
      onConfirm={handleConfirm}
      onCancel={onCancel}
      confirmDisabled={!natural || saving}
    >
      <div className={styles.editor}>
        <div
          className={styles.viewport}
          style={{ width: VIEWPORT, height: VIEWPORT }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onWheel={onWheel}
        >
          {url && (
            <img
              ref={imgRef}
              src={url}
              alt=""
              className={styles.image}
              draggable={false}
              onLoad={handleLoad}
              style={{ width: dispW, height: dispH, transform: `translate3d(${offset.x}px, ${offset.y}px, 0)` }}
            />
          )}
          <div className={styles.frame} aria-hidden="true" />
        </div>

        <label className={styles.zoom}>
          <Icon category="outlined" type="remove" />
          <input
            type="range"
            min={MIN_ZOOM}
            max={MAX_ZOOM}
            step={0.01}
            value={zoom}
            onChange={(e) => applyZoom(Number(e.target.value))}
            aria-label={t("rework.avatarCrop.zoom")}
            className={styles.zoomInput}
          />
          <Icon category="outlined" type="add" />
        </label>
      </div>
    </Dialog>
  );
}
