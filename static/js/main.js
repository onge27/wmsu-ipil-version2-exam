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

document.addEventListener('DOMContentLoaded', function() {
    const mainContent = document.querySelector('.container');
    if (mainContent) mainContent.classList.add('fade-in');
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(btn => {
        btn.addEventListener('mouseenter', function() { this.style.transform = 'translateY(-2px)'; });
        btn.addEventListener('mouseleave', function() { this.style.transform = 'translateY(0)'; });
    });
});
