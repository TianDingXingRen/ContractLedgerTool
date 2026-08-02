/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['-apple-system', 'Microsoft YaHei', 'PingFang SC', 'sans-serif'],
      },
    },
  },
  daisyui: {
    themes: ['light', 'dark'],
    logs: false,
  },
  plugins: [require('daisyui')],
};
