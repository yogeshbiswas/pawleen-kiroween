// Privacy_Banner: shown on the first visit, hidden for good once dismissed.
const KEY = "pawleenBannerDismissed";

function wasDismissed() {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    // Why: storage can be blocked (private mode). Show the banner; it is only a notice.
    return false;
  }
}

const banner = document.getElementById("privacy-banner");
const button = document.getElementById("privacy-banner-dismiss");

if (banner && button && !wasDismissed()) {
  banner.hidden = false;
  button.addEventListener("click", () => {
    banner.hidden = true;
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      // Nothing to do: the banner is already hidden for this visit.
    }
  });
}
