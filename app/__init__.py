import os

from flask import Flask, render_template

# Configuration des uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 3 * 1024 * 1024  # 5MB

# Créer les dossiers si nécessaire
os.makedirs(os.path.join('app',UPLOAD_FOLDER, 'recipes'), exist_ok=True)
os.makedirs(os.path.join('app',UPLOAD_FOLDER, 'comments'), exist_ok=True)

def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'cuisinade.sqlite'),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

    # a simple page that says hello
    @app.route('/hello')
    def hello():
        return 'Hello, World!'
    
    # @app.route('/')
    # def index():
    #     return render_template('index.html')
    
    # initialization of db
    from . import db
    db.init_app(app)

    # register the auth blueprint
    from . import auth
    app.register_blueprint(auth.bp)

    from . import recipeBook
    app.register_blueprint(recipeBook.bp)

    return app