import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from app.db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

security_questions = [
    "Quel est le nom de votre premier animal de compagnie ?",
    "Quelle est la ville où vous êtes né(e) ?",
    "Quel est le nom de jeune fille de votre mère ?",
    "Quel est votre film préféré ?",
    "Quel est le modèle de votre première voiture ?"
]

@bp.route('/register', methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        security_questions_choice = request.form['security_question']
        security_questions_answer = request.form['security_answer']
        db = get_db()
        error = None

        if not username:
            error = "Le nom d'utilisateur est requis."
        elif not password:
            error = 'Le mot de passe est requis.'
        elif not security_questions_answer or not security_questions_choice:
            error = 'La réponse à la question de sécurité est requise.'

        if error is None:
            try:
                db.execute(
                    "INSERT INTO user (username, password, security_question, security_answer) VALUES (?, ?, ?, ?)",
                    (username, generate_password_hash(password), security_questions_choice, generate_password_hash(security_questions_answer)),
                )
                db.commit()
            except db.IntegrityError:
                error = f"L'utilisateur {username} est déjà enregistré."
            else:
                flash('Votre compte a été créé avec succès')
                return redirect(url_for("auth.login"))

        flash(error, 'error')

    return render_template('auth/register.html', security_questions=security_questions)

@bp.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None
        user = db.execute(
            'SELECT * FROM user WHERE username = ?', (username,)
        ).fetchone()

        if user is None:
            error = "Nom d'utilisateur incorrect."
        elif not check_password_hash(user['password'], password):
            error = 'Mot de passe incorrect.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            flash('Vous êtes connecté avec succès')
            return redirect(url_for('recipeBook.index'))

        flash(error, 'error')

    return render_template('auth/login.html')

@bp.route('/forgot_password', methods=('GET', 'POST'))
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']
        db = get_db()
        error = None
        user = db.execute(
            'SELECT security_question FROM user WHERE username = ?', (username,)
        ).fetchone()

        if user is None:
            error = "Nom d'utilisateur incorrect."
        else:
            session['reset_username'] = username
            session['reset_security_question'] = user['security_question']
            return redirect(url_for('auth.reset_password'))
        flash(error, 'error')
    return render_template('auth/forgot_password.html', security_questions=security_questions)

@bp.route('/reset_password', methods=('GET', 'POST'))
def reset_password():
    if request.method == 'POST':
        security_answer = request.form['security_answer']
        new_password = request.form['new_password']
        db = get_db()
        error = None
        username = session.get('reset_username')
        
        if username is None:
            error = "Session expirée. Veuillez réessayer."
        else:
            user = db.execute(
                'SELECT security_answer, id FROM user WHERE username = ?', (username,)
            ).fetchone()

            if user is None:
                error = "Utilisateur non trouvé."
            elif not check_password_hash(user['security_answer'], security_answer):
                error = "Réponse à la question de sécurité incorrecte."
            elif not new_password:
                error = "Le nouveau mot de passe est requis."

        if error is None:
            db.execute(
                'UPDATE user SET password = ? WHERE id = ?',
                (generate_password_hash(new_password), user['id'])
            )
            db.commit()
            session.pop('reset_username', None)
            session.pop('reset_security_question', None)
            flash('Votre mot de passe a été réinitialisé avec succès')
            return redirect(url_for('auth.login'))

        flash(error, 'error')

    return render_template('auth/reset_password.html', question=session.get('reset_security_question'))

@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            'SELECT * FROM user WHERE id = ?', (user_id,)
        ).fetchone()

@bp.route('/logout')
def logout():
    session.clear()
    flash('Vous êtes déconnecté avec succès')
    return redirect(url_for('recipeBook.index'))

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))

        return view(**kwargs)

    return wrapped_view

def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None or g.user['is_admin'] == 0:
            flash("Vous n'avez pas les permissions nécessaires pour accéder à cette page.", 'error')
            return redirect(url_for('recipeBook.index'))

        return view(**kwargs)

    return wrapped_view