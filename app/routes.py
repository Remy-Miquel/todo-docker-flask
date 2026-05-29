import calendar
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, abort
from flask_login import login_required, current_user
from app import db
from app.models import Todo

main = Blueprint('main', __name__)

MOIS = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']


@main.route('/')
@login_required
def index():
    today = date.today()
    year  = request.args.get('year',  today.year,  type=int)
    month = request.args.get('month', today.month, type=int)

    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    todos = Todo.query.filter_by(user_id=current_user.id).order_by(Todo.created_at.desc()).all()

    debut = date(year, month, 1)
    fin   = date(year, month, calendar.monthrange(year, month)[1])

    par_jour = {}
    for t in todos:
        if t.due_date and debut <= t.due_date <= fin:
            par_jour.setdefault(t.due_date.day, []).append(t)

    semaines = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)

    pm = month - 1 if month > 1 else 12
    py = year if month > 1 else year - 1
    nm = month + 1 if month < 12 else 1
    ny = year if month < 12 else year + 1

    return render_template('index.html',
        todos=todos, today=today,
        year=year, month=month, month_name=MOIS[month],
        semaines=semaines, par_jour=par_jour,
        prev_year=py, prev_month=pm,
        next_year=ny, next_month=nm,
    )


@main.route('/todos', methods=['POST'])
@login_required
def create_todo():
    title = request.form.get('title', '').strip()
    if not title or len(title) > 200:
        abort(400)

    due_date = None
    raw = request.form.get('due_date', '').strip()
    if raw:
        try:
            due_date = date.fromisoformat(raw)
        except ValueError:
            pass

    db.session.add(Todo(title=title, due_date=due_date, user_id=current_user.id))
    db.session.commit()
    return redirect(url_for('main.index'))


@main.route('/todos/<int:todo_id>/toggle', methods=['POST'])
@login_required
def toggle_todo(todo_id):
    todo = Todo.query.filter_by(id=todo_id, user_id=current_user.id).first_or_404()
    todo.completed = not todo.completed
    db.session.commit()
    return redirect(url_for('main.index'))


@main.route('/todos/<int:todo_id>/delete', methods=['POST'])
@login_required
def delete_todo(todo_id):
    todo = Todo.query.filter_by(id=todo_id, user_id=current_user.id).first_or_404()
    db.session.delete(todo)
    db.session.commit()
    return redirect(url_for('main.index'))


@main.route('/todos/clear-done', methods=['POST'])
@login_required
def clear_done():
    Todo.query.filter_by(user_id=current_user.id, completed=True).delete()
    db.session.commit()
    return redirect(url_for('main.index'))


@main.route('/health')
def health():
    return {"status": "ok"}, 200


@main.app_errorhandler(404)
def not_found(e):
    return render_template('error.html', error="Page introuvable", code=404), 404

@main.app_errorhandler(400)
def bad_request(e):
    return render_template('error.html', error="Requête invalide", code=400), 400
