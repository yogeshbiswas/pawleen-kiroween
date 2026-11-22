module.exports = {
  content: ["./static/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: { night: "#07040d", witch: { DEFAULT: "#7c3aed", light: "#a78bfa" }, pumpkin: "#f97316" },
      fontFamily: { display: ["Creepster", "serif"], body: ["Inter", "sans-serif"] },
    },
  },
};
