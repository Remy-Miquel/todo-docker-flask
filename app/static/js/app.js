document.addEventListener('DOMContentLoaded', function () {

    // confirmation suppression
    document.querySelectorAll('.btn-del').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            if (!confirm('Supprimer cette tâche ?')) {
                e.preventDefault();
            }
        });
    });

    // filtre liste
    document.querySelectorAll('.filter-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            var f = this.dataset.filter;
            document.querySelectorAll('.todo-item').forEach(function (item) {
                if (f === 'all') {
                    item.style.display = '';
                } else {
                    item.style.display = item.dataset.status === f ? '' : 'none';
                }
            });
        });
    });

    // toggle calendrier
    var toggleBtn = document.getElementById('toggleCal');
    var calSection = document.getElementById('calSection');
    if (toggleBtn && calSection) {
        toggleBtn.addEventListener('click', function () {
            var visible = calSection.style.display === 'block';
            calSection.style.display = visible ? 'none' : 'block';
            toggleBtn.textContent = visible
                ? toggleBtn.textContent.replace('↑', '↓')
                : toggleBtn.textContent.replace('↓', '↑');
        });
    }

});
