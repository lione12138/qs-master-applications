import { translate } from "./i18n.js?v=20260626-calendar-menu";
import { state } from "./state.js";

// Translate a UI key against the tracker page's current language, falling back
// to English and then the raw key. Shared by every tracker-page module.
export function t(key) {
  return translate(state.language, key);
}
