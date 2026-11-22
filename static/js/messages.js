// Frontend-only spooky messages. Each one keeps the tone and states the plain action.
// Texts come from requirements 1.x and 2.x.

export const MESSAGES = {
  // Req 1.8: wrong file type
  fileType: "The spirits can only read photos 📸 Please choose a JPG, PNG or WebP image.",
  // Req 1.9 / 2.10: empty, undecodable, or too big to shrink
  unreadable: "The spirits could not read that file as an image 👻 Please choose a different photo (JPG, PNG or WebP).",
  // Req 2.8: pasted text was cut
  descriptionTrimmed: "Your spell was too long, so it was trimmed to 200 characters ✂️",
  // Req 1.3: shown while the photo is prepared
  darkroom: "🕯️ Developing your photo in the darkroom...",
  // Req 1.6: shorter side below 512 px
  smallPhoto: "Small photo, the result may be a bit blurry 🌙",
  // Req 1.7: tip next to the pet upload
  onePetTip: "Works best with one pet per photo 🐾",

  // Req 7.x: progress texts
  stepGatekeeping: "The Gatekeeper is inspecting your pet...",
  stepBrewing: "Brewing the costume spell...",
  stepChecking: "Checking the transformation...",
  recast: "The first spell wobbled, so we are casting it again.", // main.js adds "Attempt 2 of 2"
  ready: "🎃 Your spooky pet is ready!",
  // Req 7.7: lines that rotate every 4 seconds while brewing
  brewingLines: [
    "Stirring the cauldron...",
    "Adding a pinch of moonlight...",
    "Almost there, the spell is thickening...",
  ],
  // Req 7.13: the stream went silent for 30 s, or the network dropped
  connectionLost: "The spirits lost the connection 🕸️ Please go back to the booth and try again. Your choices are kept.",
  // Req 8.5: saving the image failed
  downloadFailed: "The spirits dropped the portrait 🕸️ Please tap the download button to try again.",
  // Notices shown if the server did not send its own text
  notVerified: "We could not double-check this spell 🔮 The portrait is yours, but it may look a bit odd.",
  wonky: "This spell came out a little wonky 🌀 You can try another costume for a better result.",
  // Fallback when the server sends an error without text
  genericError: "The spirits tripped over a cobweb 🕸️ Please go back to the booth and try again.",
};
