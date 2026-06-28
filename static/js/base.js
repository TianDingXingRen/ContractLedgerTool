tailwind.config = {
  theme: {
    extend: {
      fontFamily: {
        sans: ['-apple-system', 'Microsoft YaHei', 'PingFang SC', 'sans-serif'],
      },
    },
  },
};

function toastCenter() {
  return {
    toasts: [],
    addToast(toast) {
      this.toasts.push(toast);
      setTimeout(() => this.toasts.shift(), 3500);
    },
  };
}

document.addEventListener('alpine:init', () => {
  window.showToast = (msg, type) => {
    window.dispatchEvent(new CustomEvent('toast', {
      detail: { msg, type: type || 'success' },
    }));
  };
});
