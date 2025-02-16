document.querySelectorAll('textarea').forEach(function(textarea) {
  // Set initial height ensuring it's at least 55px
  textarea.style.height = Math.max(55, textarea.scrollHeight) + 'px';
  textarea.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.max(55, this.scrollHeight) + 'px';
  });
});
