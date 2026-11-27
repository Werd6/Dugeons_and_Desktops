(() => {
  const accents = document.querySelectorAll(".accent");
  if (!accents.length) return;

  if (!("IntersectionObserver" in window)) {
    accents.forEach((el) => el.classList.add("is-in"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-in");
          observer.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.2, rootMargin: "0px 0px -8% 0px" }
  );

  accents.forEach((el) => observer.observe(el));
})();
