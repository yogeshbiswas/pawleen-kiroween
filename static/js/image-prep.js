/*
 * Image preparation: validate, fix rotation, downscale, re-encode as JPEG.
 *
 * Manual checks (run in a desktop browser and on a phone):
 *  1. A rotated phone photo shows upright after preparing.
 *  2. A 12 MP photo ends under 10 MB and at most 2048 px on the longest side.
 *  3. A .txt file renamed to .jpg fails as "unreadable".
 *  4. A 0-byte file fails (as "unreadable").
 *
 * Console checks for the pure helpers:
 *  fitSize(4000, 3000)  -> { width: 2048, height: 1536 }
 *  fitSize(1000, 800)   -> { width: 1000, height: 800 }   (never upscales)
 *  isSmall(400, 900)    -> true    isSmall(512, 900) -> false
 */

export const MAX_SIDE = 2048; // longest side after downscale
export const MAX_BYTES = 10 * 1024 * 1024; // 10 MB limit
export const MIN_SIDE = 512; // shorter side below this -> "small" note
export const QUALITIES = [0.9, 0.8, 0.7]; // tried in order
export const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

export class PrepError extends Error {
  constructor(code) {
    super(code);
    this.name = 'PrepError';
    this.code = code; // 'type' | 'unreadable'
  }
}

// Scale so the longest side is at most MAX_SIDE. Keeps the aspect ratio.
export function fitSize(width, height, maxSide = MAX_SIDE) {
  const longest = Math.max(width, height);
  if (longest <= maxSide) return { width, height };
  const scale = maxSide / longest;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

// True when the shorter side is under 512 px.
export function isSmall(width, height) {
  return Math.min(width, height) < MIN_SIDE;
}

function canvasToBlob(canvas, quality) {
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
}

export async function prepareImage(file) {
  if (!file || !ALLOWED_TYPES.includes(file.type)) throw new PrepError('type');
  if (file.size <= 0) throw new PrepError('unreadable');

  let bitmap;
  try {
    // 'from-image' applies the EXIF rotation so the photo is upright.
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch (err) {
    // A fake .jpg (e.g. a text file) lands here.
    throw new PrepError('unreadable');
  }

  try {
    const { width, height } = fitSize(bitmap.width, bitmap.height);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff'; // transparent PNGs get a white background, not black
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(bitmap, 0, 0, width, height);
    // Always re-encode (also strips metadata); lower quality until under 10 MB.
    for (const quality of QUALITIES) {
      const blob = await canvasToBlob(canvas, quality);
      if (blob && blob.size > 0 && blob.size < MAX_BYTES) {
        return { blob, width, height, small: isSmall(width, height) };
      }
    }
    throw new PrepError('unreadable');
  } catch (err) {
    if (err instanceof PrepError) throw err;
    throw new PrepError('unreadable');
  } finally {
    if (bitmap.close) bitmap.close(); // free memory
  }
}
