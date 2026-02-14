import functools
from datetime import datetime
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, jsonify
)

from app.db import get_db
from app.auth import login_required, admin_required
from app.image_handler import save_image, delete_image

from werkzeug.exceptions import abort
from werkzeug.utils import secure_filename

import os

NB_RECIPES_FRONTPAGE = 5

bp = Blueprint('recipeBook', __name__)


@bp.route('/', methods=['GET'])
def index():
    db = get_db()
    list_recipes = db.execute("""
        SELECT  r.*, u.username 
        FROM recipes r 
        JOIN user u ON r.author_id = u.id 
        ORDER BY RANDOM()"""
    ).fetchmany(NB_RECIPES_FRONTPAGE)
    return render_template('recipe-book/index.html', recipes=list_recipes)

@bp.route('/add-recipe', methods=('POST', 'GET'))
@login_required
def add_recipe():
    if request.method == 'POST':
        # 1. Récupération des données simples pour les renvoyer en cas d'erreur
        form_data = {
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'rating': request.form.get('rating'),
            'prepTime': request.form.get('prepTime', 0),
            'cookTime': request.form.get('cookTime', 0),
            'servings': request.form.get('servings', 1),
            'difficulty': request.form.get('difficulty', 1),
            'category': request.form.get('category', -1),
            'notes': request.form.get('notes', '')
        }

        # 2. Reconstruction des listes complexes (ingrédients/instructions)
        current_ingredients = []
        i = 0
        while f'ingredients[{i}][name]' in request.form:
            current_ingredients.append({
                'name': request.form.get(f'ingredients[{i}][name]'),
                'ingredient_id': request.form.get(f'ingredients[{i}][ingredientId]'),
                'quantity': request.form.get(f'ingredients[{i}][quantity]'),
                'unit': request.form.get(f'ingredients[{i}][unit]')
            })
            i += 1

        current_instructions = []
        i = 0
        while f'instructions[{i}][text]' in request.form:
            current_instructions.append({
                'step': request.form.get(f'instructions[{i}][step]'),
                'instruction': request.form.get(f'instructions[{i}][text]')
            })
            i += 1
        
        # Validation
        error = None
        if not form_data['title']:
            error = "Le titre est requis."
        elif not form_data['description']:
            error = "La description est requise."
        
        if error is not None:
            flash(error, 'error')
            return render_template('recipe-book/addRecipe.html', 
                                 recipe=form_data, 
                                 ingredients=current_ingredients, 
                                 instructions=current_instructions)

        image_url = None
        if 'recipe_image' in request.files:
            file = request.files['recipe_image']
            if file.filename != '':
                image_url = save_image(file, 'recipes', optimize=True)
                if not image_url:
                    flash("Format d'image non valide. Utilisez PNG, JPG ou GIF.", 'error')
        
        db = get_db()
        try:
            cursor = db.execute(
                """INSERT INTO recipes (author_id, title, description, notes, author_grade, 
                   prepTime, cookTime, servings, difficulty, image_url, category) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (g.user['id'], form_data['title'], form_data['description'], form_data['notes'], 
                 form_data['rating'], form_data['prepTime'], form_data['cookTime'], 
                 form_data['servings'], form_data['difficulty'], image_url, form_data['category']),
            )
            recipe_id = cursor.lastrowid
            
            for ing in current_ingredients:
                if ing['name'] and ing['quantity'] and ing['unit']:
                    existing = db.execute(
                        'SELECT id FROM ingredient_type WHERE LOWER(name) = LOWER(?)',
                        (ing['name'],)
                    ).fetchone()
        
                    if not existing:
                        cursor = db.execute(
                            'INSERT INTO ingredient_type (name, image_url) VALUES (?, ?)',
                            (ing['name'], '/static/images/default-ingredient.jpg')
                        )
                        ing_id = cursor.lastrowid
                    else :
                        ing_id = existing["id"]
                    
                    db.execute(
                        "INSERT INTO ingredients (recipe_id, ingredient_id, quantity, unit) VALUES (?, ?, ?, ?)",
                        (recipe_id, ing_id, ing['quantity'], ing['unit']),
                    )
            
            for inst in current_instructions:
                if inst['instruction']:
                    db.execute(
                        "INSERT INTO instructions (recipe_id, step, instruction) VALUES (?, ?, ?)",
                        (recipe_id, inst['step'], inst['instruction']),
                    )
            
            db.commit()
            flash("Recette ajoutée avec succès!", 'success')
            return redirect(url_for("recipeBook.index"))
            
        except Exception as e:
            db.rollback()
            if image_url:
                delete_image(image_url)
            flash(f"Erreur lors de l'ajout : {str(e)}", 'error')
            return render_template('recipe-book/addRecipe.html', 
                                 recipe=form_data, 
                                 ingredients=current_ingredients, 
                                 instructions=current_instructions)
    
    # --- PARTIE GET (Affichage initial) ---
    # On passe un dictionnaire avec des valeurs par défaut pour éviter les "UndefinedError"
    default_recipe = {
        'title': '',
        'description': '',
        'Category': -1,
        'rating': 3,
        'prepTime': 0,
        'cookTime': 0,
        'servings': 1,
        'difficulty': 1,
        'notes': ''
    }
    return render_template('recipe-book/addRecipe.html', 
                           recipe=default_recipe, 
                           ingredients=[], 
                           instructions=[], 
                           is_edit=False)

def get_recipe(id, check_author=True):
    recipe = get_db().execute(
        "SELECT r.*, u.username FROM recipes r JOIN user u ON r.author_id = u.id WHERE r.id = ?",
        (id,)
    ).fetchone()

    if recipe is None:
        abort(404, f"Recipe id {id} doesn't exist.")

    if check_author and recipe['author_id'] != g.user['id']:
        abort(403)

    ingredients = get_db().execute(
        """SELECT r.id, ing.ingredient_id, ing_t.name, quantity, unit 
           FROM ingredients ing JOIN recipes r ON ing.recipe_id = r.id 
           JOIN ingredient_type ing_t ON ing.ingredient_id = ing_t.id 
           WHERE r.id = ?""", (id,)
    ).fetchall()

    instructions = get_db().execute(
        "SELECT id, step, instruction FROM instructions WHERE recipe_id = ?", (id,)
    ).fetchall()

    return recipe, ingredients, instructions

def get_comments(id):
    return get_db().execute(
        """SELECT c.id, c.author_id, u.username, c.comment, c.grade, c.image_url
           FROM comments c JOIN user u ON c.author_id = u.id
           WHERE c.recipe_id = ? ORDER BY c.id DESC""", (id,)
    ).fetchall()

def is_favourite(recipe_id, author_id):
    favourite = get_db().execute(
        "SELECT 1 FROM favourites WHERE recipe_id = ? AND author_id = ?", 
        (recipe_id, author_id)
    ).fetchone()
    return favourite is not None

@bp.route('/<int:id>/', methods=('POST', 'GET'))
def see_recipe(id):
    recipe, ingredients, instructions = get_recipe(id, False)
    comments = get_comments(id)
    is_fav = is_favourite(id, g.user["id"]) if g.user else False
    return render_template("recipe-book/viewRecipe.html", recipe=recipe, ingredients=ingredients, 
                           instructions=instructions, comments=comments, isFavourite=is_fav)

@bp.route('/<int:id>/comment/<int:cid>/delete', methods=('POST',))
@login_required
def delete_comment(id, cid):
    db = get_db()
    comment = db.execute("SELECT author_id, image_url FROM comments WHERE id = ?", (cid,)).fetchone()
    
    if comment is None:
        abort(404)
    if comment['author_id'] != g.user["id"]:
        abort(403)
    
    if comment['image_url']:
        delete_image(comment['image_url'])

    db.execute("DELETE FROM comments WHERE id = ?", (cid,))
    db.commit()
    flash("Commentaire supprimé !", "success")
    return redirect(url_for('recipeBook.see_recipe', id=id))

@bp.route('/<int:id>/edit', methods=('POST', 'GET'))
@login_required
def edit_recipe(id):
    recipe_db, ingredients_db, instructions_db = get_recipe(id)
    # Convert sqlite Row objects to plain dicts for JSON serialization in the template
    ingredients_for_template = [
        {
            'ingredient_id': ing['ingredient_id'],
            'name': ing['name'],
            'quantity': ing['quantity'],
            'unit': ing['unit']
        }
        for ing in ingredients_db
    ]

    instructions_for_template = [
        {
            'step': ins['step'],
            'instruction': ins['instruction']
        }
        for ins in instructions_db
    ]

    if request.method == 'POST':
        form_data = {
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'author_grade': request.form.get('rating'),
            'prepTime': request.form.get('prepTime', 0),
            'cookTime': request.form.get('cookTime', 0),
            'servings': request.form.get('servings', 1),
            'difficulty': request.form.get('difficulty', 1),
            'category': request.form.get('category', 0),
            'notes': request.form.get('notes', '')
        }

        current_ingredients = []
        i = 0
        while f'ingredients[{i}][name]' in request.form:
            current_ingredients.append({
                'name': request.form.get(f'ingredients[{i}][name]'),
                'quantity': request.form.get(f'ingredients[{i}][quantity]'),
                'unit': request.form.get(f'ingredients[{i}][unit]')
            })
            i += 1

        current_instructions = []
        i = 0
        while f'instructions[{i}][text]' in request.form:
            current_instructions.append({
                'step': request.form.get(f'instructions[{i}][step]'),
                'instruction': request.form.get(f'instructions[{i}][text]')
            })
            i += 1

        error = None
        if not form_data['title']:
            error = "Le titre est requis."
        
        if error:
            flash(error, 'error')
            return render_template('recipe-book/addRecipe.html', recipe=form_data, 
                                 ingredients=current_ingredients, instructions=current_instructions, is_edit=True)

        image_url = recipe_db['image_url']
        if 'recipe_image' in request.files:
            file = request.files['recipe_image']
            if file.filename != '':
                new_img = save_image(file, 'recipes', optimize=True)
                if new_img:
                    if image_url: delete_image(image_url)
                    image_url = new_img
        
        if request.form.get('remove_image') == 'true':
            if image_url: delete_image(image_url)
            image_url = None
        
        db = get_db()
        try:
            db.execute(
                """UPDATE recipes SET title=?, description=?, notes=?, author_grade=?, 
                   prepTime=?, cookTime=?, servings=?, difficulty=?, image_url=?, category=? WHERE id=?""",
                (form_data['title'], form_data['description'], form_data['notes'], form_data['author_grade'], 
                 form_data['prepTime'], form_data['cookTime'], form_data['servings'], 
                 form_data['difficulty'], image_url, form_data['category'], id)
            )

            db.execute("DELETE FROM ingredients WHERE recipe_id = ?", (id,))
            for ing in current_ingredients:
                existing = db.execute('SELECT id FROM ingredient_type WHERE LOWER(name)=LOWER(?)', (ing['name'],)).fetchone()
                ing_id = existing['id'] if existing else db.execute('INSERT INTO ingredient_type (name) VALUES (?)', (ing['name'],)).lastrowid
                db.execute("INSERT INTO ingredients (recipe_id, ingredient_id, quantity, unit) VALUES (?,?,?,?)",
                           (id, ing_id, ing['quantity'], ing['unit']))

            db.execute("DELETE FROM instructions WHERE recipe_id = ?", (id,))
            for inst in current_instructions:
                db.execute("INSERT INTO instructions (recipe_id, step, instruction) VALUES (?,?,?)",
                           (id, inst['step'], inst['instruction']))

            db.commit()
            flash("Recette mise à jour !", 'success')
            return redirect(url_for('recipeBook.see_recipe', id=id))
        except Exception as e:
            db.rollback()
            flash(f"Erreur : {str(e)}", 'error')

    return render_template('recipe-book/addRecipe.html', recipe=recipe_db, 
                           ingredients=ingredients_for_template, instructions=instructions_for_template, is_edit=True)

@bp.route('/<int:id>/delete', methods=('POST', 'GET'))
@login_required
def delete_recipe(id):
    db = get_db()
    recipe = db.execute("SELECT author_id, image_url FROM recipes WHERE id = ?", (id,)).fetchone()
    if recipe and recipe['author_id'] == g.user["id"]:
        if recipe['image_url']: delete_image(recipe['image_url'])
        db.execute("DELETE FROM recipes WHERE id = ?", (id,))
        db.execute("DELETE FROM ingredients WHERE recipe_id = ?", (id,))
        db.execute("DELETE FROM instructions WHERE recipe_id = ?", (id,))
        db.commit()
        flash("Recette supprimée.", "success")
    return redirect(url_for('recipeBook.index'))

@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    g.user = get_db().execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone() if user_id else None

@bp.route('/search', methods=['GET'])
def search_recipes():
    db = get_db()
    q = request.args.get('q', '').strip()
    # Logique simplifiée pour l'exemple, conservez votre bloc SQL dynamique ici
    recipes = db.execute("SELECT r.*, u.username FROM recipes r JOIN user u ON r.author_id = u.id WHERE r.title LIKE ?", (f'%{q}%',)).fetchall()
    return render_template('recipe-book/search.html', recipes=recipes, search_query=q)

@bp.route('/api/ingredients', methods=['GET'])
def get_ingredients():
    ingredients = get_db().execute('SELECT id, name FROM ingredient_type ORDER BY name ASC').fetchall()
    return jsonify([{'id': i['id'], 'name': i['name']} for i in ingredients])

@bp.route('/api/toggle_favourites/<int:id>', methods=['POST'])
@login_required
def toggle_favourite(id):
    db = get_db()
    if is_favourite(id, g.user["id"]):
        db.execute("DELETE FROM favourites WHERE recipe_id = ? AND author_id = ?", (id, g.user["id"]))
    else:
        db.execute("INSERT INTO favourites (recipe_id, author_id) VALUES (?, ?)", (id, g.user["id"]))
    db.commit()
    return redirect(url_for('recipeBook.see_recipe', id=id))

@bp.route('/api/<int:id>/add_comment', methods=['POST'])
@login_required
def add_comment(id):
    db = get_db()
    comment = request.form.get("comment")
    grade = request.form.get("grade")
    image_url = None
    if 'comment_image' in request.files:
        file = request.files['comment_image']
        if file.filename != '': image_url = save_image(file, 'comments', optimize=True)
    
    if comment and grade:
        db.execute("INSERT INTO comments (recipe_id, author_id, comment, grade, image_url) VALUES (?,?,?,?,?)",
                   (id, g.user['id'], comment, grade, image_url))
        db.commit()
        flash("Commentaire ajouté !", 'success')
    return redirect(url_for('recipeBook.see_recipe', id=id))

@bp.route('/admin')
@login_required
@admin_required
def admin_page():
    """Display admin dashboard with statistics and management options"""
    db = get_db()
    
    # Get statistics
    stats = {
        'total_users': db.execute('SELECT COUNT(*) as count FROM user').fetchone()['count'],
        'total_recipes': db.execute('SELECT COUNT(*) as count FROM recipes').fetchone()['count'],
        'total_comments': db.execute('SELECT COUNT(*) as count FROM comments').fetchone()['count'],
        'total_ingredients': db.execute('SELECT COUNT(*) as count FROM ingredient_type').fetchone()['count'],
        'total_favourites': db.execute('SELECT COUNT(*) as count FROM favourites').fetchone()['count'],
    }
    
    # Get recent recipes
    recent_recipes = db.execute("""
        SELECT r.id, r.title, u.username, r.added, r.author_grade
        FROM recipes r
        JOIN user u ON r.author_id = u.id
        ORDER BY r.added DESC
        LIMIT 10
    """).fetchall()
    
    # Get recent comments
    recent_comments = db.execute("""
        SELECT c.id, c.comment, u.username, c.grade, r.title, c.recipe_id
        FROM comments c
        JOIN user u ON c.author_id = u.id
        JOIN recipes r ON c.recipe_id = r.id
        ORDER BY c.id DESC
        LIMIT 10
    """).fetchall()
    
    # Get most rated recipes
    top_recipes = db.execute("""
        SELECT r.id, r.title, u.username, r.author_grade, COUNT(c.id) as comment_count
        FROM recipes r
        JOIN user u ON r.author_id = u.id
        LEFT JOIN comments c ON r.id = c.recipe_id
        GROUP BY r.id
        ORDER BY r.author_grade DESC
        LIMIT 10
    """).fetchall()
    
    # Get most active users
    active_users = db.execute("""
        SELECT u.id, u.username, COUNT(r.id) as recipe_count, COUNT(c.id) as comment_count
        FROM user u
        LEFT JOIN recipes r ON u.id = r.author_id
        LEFT JOIN comments c ON u.id = c.author_id
        GROUP BY u.id
        ORDER BY (COUNT(r.id) + COUNT(c.id)) DESC
        LIMIT 10
    """).fetchall()
    
    # Get all users for management
    all_users = db.execute("""
        SELECT u.id, u.username, 
               COUNT(DISTINCT r.id) as recipe_count,
               COUNT(DISTINCT c.id) as comment_count,
               COALESCE(u.is_admin, 0) as is_admin
        FROM user u
        LEFT JOIN recipes r ON u.id = r.author_id
        LEFT JOIN comments c ON u.id = c.author_id
        GROUP BY u.id
        ORDER BY u.username
    """).fetchall()
    
    return render_template('admin.html', 
                         stats=stats,
                         recent_recipes=recent_recipes,
                         recent_comments=recent_comments,
                         top_recipes=top_recipes,
                         active_users=active_users,
                         all_users=all_users)

@bp.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
def toggle_user_admin(user_id):
    """Toggle admin status for a user"""
    db = get_db()
    
    # Prevent admin from removing their own admin status
    if user_id == g.user['id']:
        flash("Vous ne pouvez pas modifier votre propre statut administrateur.", 'error')
        return redirect(url_for('recipeBook.admin_page'))
    
    user = db.execute('SELECT is_admin FROM user WHERE id = ?', (user_id,)).fetchone()
    if user is None:
        abort(404)
    
    new_status = 0 if (user['is_admin'] or 0) else 1
    db.execute('UPDATE user SET is_admin = ? WHERE id = ?', (new_status, user_id))
    db.commit()
    
    status_text = "administrateur" if new_status else "utilisateur régulier"
    flash(f"Statut de l'utilisateur modifié en {status_text}.", 'success')
    return redirect(url_for('recipeBook.admin_page'))

@bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user and all their content"""
    db = get_db()
    
    # Prevent admin from deleting themselves
    if user_id == g.user['id']:
        flash("Vous ne pouvez pas supprimer votre propre compte.", 'error')
        return redirect(url_for('recipeBook.admin_page'))
    
    user = db.execute('SELECT id FROM user WHERE id = ?', (user_id,)).fetchone()
    if user is None:
        abort(404)
    
    try:
        # Delete user's recipes and related content
        recipes = db.execute('SELECT id, image_url FROM recipes WHERE author_id = ?', (user_id,)).fetchall()
        for recipe in recipes:
            if recipe['image_url']:
                delete_image(recipe['image_url'])
            db.execute('DELETE FROM ingredients WHERE recipe_id = ?', (recipe['id'],))
            db.execute('DELETE FROM instructions WHERE recipe_id = ?', (recipe['id'],))
        
        # Delete user's comments
        comments = db.execute('SELECT image_url FROM comments WHERE author_id = ?', (user_id,)).fetchall()
        for comment in comments:
            if comment['image_url']:
                delete_image(comment['image_url'])
        
        # Delete recipes first due to foreign key constraints
        db.execute('DELETE FROM recipes WHERE author_id = ?', (user_id,))
        db.execute('DELETE FROM comments WHERE author_id = ?', (user_id,))
        db.execute('DELETE FROM favourites WHERE author_id = ?', (user_id,))
        
        # Finally delete the user
        db.execute('DELETE FROM user WHERE id = ?', (user_id,))
        db.commit()
        
        flash("Utilisateur et tous ses contenus supprimés.", 'success')
    except Exception as e:
        db.rollback()
        flash(f"Erreur lors de la suppression : {str(e)}", 'error')
    
    return redirect(url_for('recipeBook.admin_page'))

@bp.route('/admin/comments/<int:comment_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_comment(comment_id):
    """Admin deletion of a comment"""
    db = get_db()
    comment = db.execute('SELECT image_url, recipe_id FROM comments WHERE id = ?', (comment_id,)).fetchone()
    
    if comment is None:
        abort(404)
    
    if comment['image_url']:
        delete_image(comment['image_url'])
    
    db.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    db.commit()
    
    flash("Commentaire supprimé par l'administrateur.", 'success')
    return redirect(url_for('recipeBook.admin_page'))

@bp.route('/admin/recipes/<int:recipe_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_recipe(recipe_id):
    """Admin deletion of a recipe"""
    db = get_db()
    recipe = db.execute('SELECT image_url FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
    
    if recipe is None:
        abort(404)
    
    try:
        if recipe['image_url']:
            delete_image(recipe['image_url'])
        
        db.execute('DELETE FROM ingredients WHERE recipe_id = ?', (recipe_id,))
        db.execute('DELETE FROM instructions WHERE recipe_id = ?', (recipe_id,))
        db.execute('DELETE FROM comments WHERE recipe_id = ?', (recipe_id,))
        db.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
        db.commit()
        
        flash("Recette supprimée par l'administrateur.", 'success')
    except Exception as e:
        db.rollback()
        flash(f"Erreur : {str(e)}", 'error')
    
    return redirect(url_for('recipeBook.admin_page'))

@bp.route('/admin/stats/api', methods=['GET'])
@login_required
@admin_required
def admin_stats_api():
    """API endpoint for detailed statistics"""
    db = get_db()
    
    # Recipes by category (if category exists)
    recipes_by_difficulty = db.execute("""
        SELECT difficulty, COUNT(*) as count
        FROM recipes
        GROUP BY difficulty
        ORDER BY difficulty
    """).fetchall()
    
    # Average recipe ratings
    avg_rating = db.execute("""
        SELECT AVG(author_grade) as avg_rating
        FROM recipes
    """).fetchone()
    
    # Comments statistics
    comments_stats = db.execute("""
        SELECT 
            AVG(grade) as avg_grade,
            COUNT(*) as total,
            MAX(grade) as max_grade,
            MIN(grade) as min_grade
        FROM comments
    """).fetchone()
    
    return jsonify({
        'recipes_by_difficulty': [dict(row) for row in recipes_by_difficulty],
        'avg_recipe_rating': dict(avg_rating),
        'comments_stats': dict(comments_stats)
    })