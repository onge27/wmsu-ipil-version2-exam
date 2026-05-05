// Auto-dismiss flash messages (handled in base.html)
// Legacy timer function kept for compatibility
function startTimer(durationMinutes, displayElement, formId) {
    let time = durationMinutes * 60;
    const timerDisplay = document.getElementById(displayElement);
    const interval = setInterval(() => {
        const minutes = Math.floor(time / 60);
        const seconds = time % 60;
        timerDisplay.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        if (time <= 0) {
            clearInterval(interval);
            document.getElementById(formId).submit();
        }
        time--;
    }, 1000);
}
