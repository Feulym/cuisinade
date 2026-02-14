import functools
from datetime import datetime
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, jsonify
)

from app.db import get_db
from app.auth import login_required
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
        title = request.form['title']
        description = request.form['description']
        author_rating = request.form['rating']
        prepTime = request.form.get('prepTime', 0)
        cookTime = request.form.get('cookTime', 0)
        servings = request.form.get('servings', 1)
        difficulty = request.form.get('difficulty', 1)
        note = request.form.get('notes', None)
        
        # Gérer l'upload de l'image
        image_url = None
        if 'recipe_image' in request.files:
            file = request.files['recipe_image']
            if file.filename != '':
                image_url = save_image(file, 'recipes', optimize=True)
                if not image_url:
                    flash("Format d'image non valide. Utilisez PNG, JPG ou GIF.", 'error')
        
        db = get_db()
        error = None
        
        if not title:
            error = "Le titre est requis."
        elif not description:
            error = "La description est requise."
        
        if error is not None:
            flash(error, 'error')
            return render_template('recipe-book/addRecipe.html')
        
        try:
            # STEP 1: Insert recipe's general info in recipes first to get recipe_id
            cursor = db.execute(
                """INSERT INTO recipes (author_id, title, description, notes, author_grade, 
                   prepTime, cookTime, servings, difficulty, image_url) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (g.user['id'], title, description, note, author_rating, 
                 prepTime, cookTime, servings, difficulty, image_url),
            )
            recipe_id = cursor.lastrowid
            
            # STEP 2: Insert ingredients (now we have recipe_id)
            i = 0
            while f'ingredients[{i}][name]' in request.form:
                ing_name = request.form.get(f'ingredients[{i}][name]')
                ing_id = request.form.get(f'ingredients[{i}][ingredientId]')
                quantity = request.form.get(f'ingredients[{i}][quantity]')
                unit = request.form.get(f'ingredients[{i}][unit]')
                
                if ing_name and quantity and unit:
                    # Check if ingredient already exists (case-insensitive)
                    existing = db.execute(
                        'SELECT id, name FROM ingredient_type WHERE LOWER(name) = LOWER(?)',
                        (ing_name,)
                    ).fetchone()
        
                    # If ingredient doesn't exist in DB, create it first
                    if (not ing_id or ing_id == '' or ing_id == 'null') and not existing:
                        print(f"Creating new ingredient: {ing_name}")
                        cursor = db.execute(
                            'INSERT INTO ingredient_type (name, image_url) VALUES (?, ?)',
                            (ing_name, '/static/images/default-ingredient.jpg')
                        )
                        ing_id = cursor.lastrowid
                    else :
                        ing_id = existing["id"]
                    
                    print(f"Inserting ingredient: recipe_id={recipe_id}, ingredient_id={ing_id}, quantity={quantity}, unit={unit}")
                    db.execute(
                        "INSERT INTO ingredients (recipe_id, ingredient_id, quantity, unit) VALUES (?, ?, ?, ?)",
                        (recipe_id, ing_id, quantity, unit),
                    )
                i += 1
            
            # STEP 3: Insert instructions (now we have recipe_id)
            i = 0
            while f'instructions[{i}][text]' in request.form:
                inst_step = request.form.get(f'instructions[{i}][step]')
                inst_text = request.form.get(f'instructions[{i}][text]')
                
                if inst_text:
                    print(f"Inserting instruction: recipe_id={recipe_id}, step={inst_step}, text={inst_text[:30]}...")
                    db.execute(
                        "INSERT INTO instructions (recipe_id, step, instruction) VALUES (?, ?, ?)",
                        (recipe_id, inst_step, inst_text),
                    )
                i += 1
            
            # STEP 4: Commit all changes at once
            db.commit()
            flash("Recette ajoutée avec succès!", 'success')
            return redirect(url_for("recipeBook.index"))
            
        except Exception as e:
            db.rollback()
            # Supprimer l'image si erreur
            if image_url:
                delete_image(image_url)
            print(f"Exception occurred: {str(e)}")
            flash(f"Erreur lors de l'ajout de la recette: {str(e)}", 'error')
            return render_template('recipe-book/addRecipe.html')
    
    return render_template('recipe-book/addRecipe.html')

def get_recipe(id, check_author=True):
    recipe_querry = """
            SELECT r.*, u.username
             FROM recipes r JOIN user u ON r.author_id = u.id
             WHERE r.id = ?
    """
    print("Recipe querry : ", recipe_querry)
    recipe = get_db().execute(recipe_querry,
        (id,)
    ).fetchone()

    if recipe is None:
        abort(404, f"Recipe id {id} doesn't exist.")

    if check_author and recipe['author_id'] != g.user['id']:
        abort(403)

    ing_querry = """
        SELECT r.id, ing.ingredient_id, ing_t.name, quantity, unit 
         FROM ingredients ing JOIN recipes r ON ing.recipe_id = r.id 
         JOIN ingredient_type ing_t ON ing.ingredient_id = ing_t.id 
         WHERE r.id = ?
    """
    print("Ingredient querry : ", ing_querry)
    ingredients = get_db().execute(
        ing_querry,
        (id,)
    ).fetchall()

        ins_querry = """
            SELECT step, instruction
             FROM instructions
             WHERE recipe_id = ?
        """
    print("Instruction querry : ", ins_querry)
    instructions = get_db().execute(
        ins_querry,
        (id,)
    ).fetchall()

    return recipe, ingredients, instructions

def get_comments(id):
    querry = """
        SELECT c.id, c.author_id, u.username, c.comment, c.grade, c.image_url
         FROM comments c 
         JOIN recipes r ON c.recipe_id = r.id
         JOIN user u ON c.author_id = u.id
         WHERE r.id = ?
         ORDER BY c.id DESC
    """
    print("Comments querry : ", querry)
    comments = get_db().execute(
        querry,
        (id,)
    ).fetchall()

    return comments

def is_favourite(recipe_id, author_id):
    querry = """
        SELECT * FROM favourites WHERE recipe_id = ? AND author_id = ?
    """
    print("Favourite querry : ", querry)
    favourite = get_db().execute(
        querry, (recipe_id, author_id)
    ).fetchone()
    print('In the db ? ', favourite != None)
    return favourite != None

@bp.route('/<int:id>/', methods=('POST', 'GET'))
def see_recipe(id):
    recipe, ingredients, instructions = get_recipe(id, False)
    comments = get_comments(id)
    if g.user :
        is_fav = is_favourite(id, g.user["id"])
        print('Is favourite ? ', )
    else :
        is_fav = False
    return render_template("recipe-book/viewRecipe.html", recipe=recipe, ingredients=ingredients, instructions=instructions, 
                           comments=comments, isFavourite=is_fav)

@bp.route('/<int:id>/comment/<int:cid>/delete', methods=('POST',))
@login_required
def delete_comment(id, cid):
    db = get_db()
    
    # Get the comment to check ownership
    comment = db.execute(
        "SELECT author_id, image_url FROM comments WHERE id = ?",
        (cid,)
    ).fetchone()
    
    # Check if comment exists
    if comment is None:
        abort(404, f"Comment id {cid} doesn't exist.")
    
    # Check if current user is the author (FIXED: access the field correctly)
    if comment['author_id'] != g.user["id"]:
        abort(403, "You don't have permission to delete this comment.")
    
    print("DEBUG DELETE IMAGE: ", comment['image_url'])
    if comment['image_url'] :
        # Delete the comment
        delete_image(comment['image_url'])

    # Delete the comment
    db.execute(
        "DELETE FROM comments WHERE id = ?",
        (cid,)  # Fixed: removed extra parenthesis, should be (cid,) not (cid)
    )
    
    db.commit()
    
    flash("Comment deleted successfully!", "success")
    
    # Redirect back to the recipe page
    return redirect(url_for('recipeBook.see_recipe', id=id))

@bp.route('/<int:id>/edit', methods=('POST', 'GET'))
@login_required
def edit_recipe(id):
    recipe, ingredients, instructions = get_recipe(id)

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        author_rating = request.form['rating']
        prepTime = request.form.get('prepTime', 0)
        cookTime = request.form.get('cookTime', 0)
        servings = request.form.get('servings', 1)
        difficulty = request.form.get('difficulty', 1)
        note = request.form.get('notes', None)
        
        # Gérer la nouvelle image
        image_url = recipe['image_url']  # Garder l'ancienne par défaut
        if 'recipe_image' in request.files:
            file = request.files['recipe_image']
            if file.filename != '':
                new_image_url = save_image(file, 'recipes', optimize=True)
                if new_image_url:
                    # Supprimer l'ancienne image
                    if image_url:
                        delete_image(image_url)
                    image_url = new_image_url
        
        # Vérifier si l'utilisateur veut supprimer l'image
        if request.form.get('remove_image') == 'true':
            if image_url:
                delete_image(image_url)
            image_url = None
        
        db = get_db()
        error = None

        if not title:
            error = "Le titre est requis."
        elif not description:
            error = "La description est requise."

        if error is not None:
            flash(error, 'error')
        else:
            try:
                # 1. Update general recipe info
                db.execute(
                    """UPDATE recipes SET title = ?, description = ?, notes = ?, author_grade = ?, 
                       prepTime = ?, cookTime = ?, servings = ?, difficulty = ?, image_url = ?
                       WHERE id = ?""",
                    (title, description, note, author_rating, prepTime, cookTime, 
                     servings, difficulty, image_url, id)
                )

                # 2. Update Ingredients: Delete old ones and insert new ones
                db.execute("DELETE FROM ingredients WHERE recipe_id = ?", (id,))
                
                i = 0
                while f'ingredients[{i}][name]' in request.form:
                    ing_name = request.form.get(f'ingredients[{i}][name]')
                    ing_id = request.form.get(f'ingredients[{i}][ingredientId]')
                    quantity = request.form.get(f'ingredients[{i}][quantity]')
                    unit = request.form.get(f'ingredients[{i}][unit]')
                    
                    # Check if ingredient already exists (case-insensitive)
                    existing = db.execute(
                        'SELECT id, name FROM ingredient_type WHERE LOWER(name) = LOWER(?)',
                        (ing_name,)
                    ).fetchone()

                    if ing_name and quantity and unit:
                        # Create ingredient type if it's new
                        if not existing and (not ing_id or ing_id == '' or ing_id == 'null'):
                            cursor = db.execute(
                                'INSERT INTO ingredient_type (name, image_url) VALUES (?, ?)',
                                (ing_name, '/static/images/default-ingredient.jpg')
                            )
                            ing_id = cursor.lastrowid
                        
                        db.execute(
                            "INSERT INTO ingredients (recipe_id, ingredient_id, quantity, unit) VALUES (?, ?, ?, ?)",
                            (id, ing_id, quantity, unit),
                        )
                    i += 1

                # 3. Update Instructions: Delete old ones and insert new ones
                db.execute("DELETE FROM instructions WHERE recipe_id = ?", (id,))
                
                i = 0
                while f'instructions[{i}][text]' in request.form:
                    inst_step = request.form.get(f'instructions[{i}][step]')
                    inst_text = request.form.get(f'instructions[{i}][text]')
                    
                    if inst_text:
                        db.execute(
                            "INSERT INTO instructions (recipe_id, step, instruction) VALUES (?, ?, ?)",
                            (id, inst_step, inst_text),
                        )
                    i += 1

                db.commit()
                flash("Recette mise à jour avec succès !", 'success')
                return redirect(url_for('recipeBook.see_recipe', id=id))

            except Exception as e:
                db.rollback()
                print(f"Update failed: {str(e)}")
                flash(f"Erreur lors de la modification: {str(e)}", 'error')

    return render_template('recipe-book/addRecipe.html', 
                           recipe=recipe, 
                           ingredients=ingredients, 
                           instructions=instructions,
                           is_edit=True)

@bp.route('/<int:id>/delete', methods=('POST', 'GET'))
@login_required
def delete_recipe(id):
    db = get_db()
    
    recipe = db.execute(
        "SELECT author_id, image_url FROM recipes WHERE id = ?",
        (id,)
    ).fetchone()
    
    if recipe is None:
        abort(404, f"Recipe id {id} doesn't exist.")
    
    if recipe['author_id'] != g.user["id"]:
        abort(403, "You don't have permission to delete this recipe.")
    
    # Supprimer l'image associée
    if recipe['image_url']:
        delete_image(recipe['image_url'])
    
    db.execute("DELETE FROM recipes WHERE id = ?", (id,))
    db.execute("DELETE FROM comments WHERE recipe_id = ?", (id,))
    db.execute("DELETE FROM favourites WHERE recipe_id = ?", (id,))
    db.execute("DELETE FROM instructions WHERE recipe_id = ?", (id,))
    db.execute("DELETE FROM ingredients WHERE recipe_id = ?", (id,))
    db.commit()
    
    flash("Recette supprimée avec succès!", "success")
    return redirect(url_for('recipeBook.index'))

@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            'SELECT * FROM user WHERE id = ?', (user_id,)
        ).fetchone()

@bp.route('/search', methods=['GET'])
def search_recipes():
    """Page de recherche avec filtres avancés"""
    db = get_db()
    
    # Récupération des paramètres de recherche
    search_query = request.args.get('q', '').strip()
    difficulty = request.args.get('difficulty', '')
    max_prep_time = request.args.get('max_prep_time', '')
    max_cook_time = request.args.get('max_cook_time', '')
    min_servings = request.args.get('min_servings', '')
    min_rating = request.args.get('min_rating', '')
    
    # Construction de la requête SQL dynamique
    query = '''
        SELECT r.*, u.username 
        FROM recipes r 
        JOIN user u ON r.author_id = u.id 
        WHERE 1=1
    '''
    params = []
    
    # Filtre de recherche textuelle
    if search_query:
        query += ' AND (r.title LIKE ? OR r.description LIKE ?)'
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    
    # Filtre de difficulté
    if difficulty:
        query += ' AND r.difficulty = ?'
        params.append(int(difficulty))
    
    # Filtre temps de préparation
    if max_prep_time:
        query += ' AND r.prepTime <= ?'
        params.append(int(max_prep_time))
    
    # Filtre temps de cuisson
    if max_cook_time:
        query += ' AND r.cookTime <= ?'
        params.append(int(max_cook_time))
    
    # Filtre nombre de personnes
    if min_servings:
        query += ' AND r.servings >= ?'
        params.append(int(min_servings))
    
    # Filtre note minimale
    if min_rating:
        query += ' AND r.author_grade >= ?'
        params.append(int(min_rating))
    
    # Tri par défaut (le plus récent) - Le tri sera géré en JavaScript
    query += ' ORDER BY r.added DESC'
    
    print("Search query:", query)
    print("Params:", params)
    
    try:
        recipes = db.execute(query, params).fetchall()
    except Exception as e:
        print(f"Search error: {str(e)}")
        flash("Erreur lors de la recherche", 'error')
        recipes = []
    
    # Statistiques pour affichage
    total_results = len(recipes)
    
    return render_template('recipe-book/search.html',
                         recipes=recipes,
                         search_query=search_query,
                         difficulty=difficulty,
                         max_prep_time=max_prep_time,
                         max_cook_time=max_cook_time,
                         min_servings=min_servings,
                         min_rating=min_rating,
                         total_results=total_results)

# ============================================
# API ROUTES FOR AJAX CALLS
# ============================================

@bp.route('/api/ingredients', methods=['GET'])
def get_ingredients():
    """
    Fetch all ingredients from the database for autocomplete
    Returns JSON array of {id, name} objects
    """
    db = get_db()
    
    try:
        ingredients = db.execute(
            'SELECT id, name FROM ingredient_type ORDER BY name ASC'
        ).fetchall()
        
        # Convert to list of dictionaries
        ingredients_list = [
            {'id': ing['id'], 'name': ing['name']} 
            for ing in ingredients
        ]
        
        return jsonify(ingredients_list)
    
    except Exception as e:
        print(f"Error fetching ingredients: {e}")
        return jsonify({'error': 'Failed to fetch ingredients'}), 500


@bp.route('/api/ingredients/create', methods=['POST'])
def create_ingredient():
    """
    Create a new ingredient type in the database
    Expects JSON: {"name": "Ingredient Name"}
    Returns JSON: {"id": 123, "name": "Ingredient Name"}
    """
    db = get_db()
    
    # Get data from request
    data = request.get_json()
    
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400
    
    name = data['name'].strip()
    
    if not name:
        return jsonify({'error': 'Name cannot be empty'}), 400
    
    try:
        # Check if ingredient already exists (case-insensitive)
        existing = db.execute(
            'SELECT id, name FROM ingredient_type WHERE LOWER(name) = LOWER(?)',
            (name,)
        ).fetchone()
        
        if existing:
            # Return existing ingredient instead of creating duplicate
            return jsonify({'id': existing['id'], 'name': existing['name']})
        
        # Insert new ingredient with default image
        cursor = db.execute(
            'INSERT INTO ingredient_type (name, image_url) VALUES (?, ?)',
            (name, '/static/images/default-ingredient.jpg')
        )
        db.commit()
        
        new_id = cursor.lastrowid
        
        return jsonify({'id': new_id, 'name': name}), 201
    
    except Exception as e:
        db.rollback()
        print(f"Error creating ingredient: {e}")
        return jsonify({'error': 'Failed to create ingredient'}), 500


# Optional: Get units list
@bp.route('/api/units', methods=['GET'])
def get_units():
    """
    Returns list of measurement units
    """
    units = [
        'g', 'kg', 'mg',
        'ml', 'L', 'cl',
        'cuillères à soupe', 'cuillères à café',
        'tasse(s)', 'verre(s)',
        'pièce(s)', 'tranche(s)',
        'pincée(s)', 'poignée(s)',
        'bouquet(s)', 'botte(s)'
    ]
    
    return jsonify(units)

@bp.route('/api/toggle_favourites/<int:id>', methods=['POST'])
@login_required
def toggle_favourite(id):
    db = get_db()
    if is_favourite(id, g.user["id"]):
        db.execute(
            "DELETE FROM favourites WHERE recipe_id = ? AND author_id = ?", 
            (id, g.user["id"])
        )
    else:
        db.execute(
            "INSERT INTO favourites (recipe_id, author_id) VALUES (?, ?)", 
            (id, g.user["id"])
        )

    db.commit()
    # Redirect back to the recipe page instead of calling the function directly
    return redirect(url_for('recipeBook.see_recipe', id=id))

@bp.route('/api/<int:id>/add_comment', methods=['POST'])
@login_required
def add_comment(id):
    db = get_db()
    user_id = g.user['id']
    rating = request.form["grade"]
    comment = request.form["comment"]
    
    # Gérer l'upload de l'image du commentaire
    image_url = None
    if 'comment_image' in request.files:
        file = request.files['comment_image']
        if file.filename != '':
            image_url = save_image(file, 'comments', optimize=True)
    
    error = None
    if not comment:
        error = 'Le commentaire est requis.'
    if not rating:
        error = 'La note est requise'
    
    if error:
        flash(error, 'error')
        return redirect(url_for('recipeBook.see_recipe', id=id))
    
    db.execute(
        """INSERT INTO comments (recipe_id, author_id, comment, grade, image_url) 
           VALUES (?, ?, ?, ?, ?)""",
        (id, user_id, comment, rating, image_url)
    )
    db.commit()
    
    flash("Commentaire ajouté avec succès!", 'success')
    return redirect(url_for('recipeBook.see_recipe', id=id))