export type ThemePreference = "system" | "light" | "dark";

const STORAGE_KEY = "atp-theme";

function stored(): ThemePreference {
	try {
		const v = localStorage.getItem(STORAGE_KEY);
		if (v === "light" || v === "dark") return v;
	} catch {}
	return "system";
}

const query = window.matchMedia("(prefers-color-scheme: dark)");

class Theme {
	preference = $state<ThemePreference>(stored());
	#systemDark = $state(query.matches);

	constructor() {
		query.addEventListener("change", (e) => {
			this.#systemDark = e.matches;
		});
	}

	/** The mode actually on screen. */
	get mode(): "light" | "dark" {
		if (this.preference === "system") return this.#systemDark ? "dark" : "light";
		return this.preference;
	}

	set(preference: ThemePreference) {
		this.preference = preference;
		try {
			if (preference === "system") localStorage.removeItem(STORAGE_KEY);
			else localStorage.setItem(STORAGE_KEY, preference);
		} catch {}
		if (preference === "system") delete document.documentElement.dataset.theme;
		else document.documentElement.dataset.theme = preference;
	}

	/** Cycle light -> dark -> system. */
	cycle() {
		const next: ThemePreference =
			this.preference === "light" ? "dark" : this.preference === "dark" ? "system" : "light";
		this.set(next);
	}
}

export const theme = new Theme();
