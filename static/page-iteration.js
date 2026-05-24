// Iteration page: when the user picks yes/no, swap the dynamic message and
// reset the editable fields. Defaults for the "no" branch come from data-*
// attrs so the JS file stays free of Jinja interpolation.
(() => {
  const form = document.querySelector("form[data-iteration-form]");
  if (!form) return;

  const defaults = {
    nextSteps: form.dataset.defaultNextSteps || "",
    reward: form.dataset.defaultReward || "",
  };

  const dynamicMessage = document.getElementById("dynamicMessage");
  const txtWasDone = document.getElementById("txtWasDone");
  const txtNextStep = document.getElementById("txtNextStep");
  const txtReward = document.getElementById("txtReward");

  function update(value) {
    if (!dynamicMessage) return;
    if (value === "yes") {
      dynamicMessage.textContent = "Banana!";
      if (txtWasDone) txtWasDone.value = "";
      if (txtNextStep) txtNextStep.value = "";
      if (txtReward) txtReward.value = "";
    } else if (value === "no") {
      dynamicMessage.textContent = "Baboon is angry";
      if (txtWasDone) txtWasDone.value = "";
      if (txtNextStep) txtNextStep.value = defaults.nextSteps;
      if (txtReward) txtReward.value = defaults.reward;
    }
  }

  document.querySelectorAll('input[name="completed"]').forEach((input) => {
    input.addEventListener("change", () => update(input.value));
  });
})();
