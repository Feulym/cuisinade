DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS product;
DROP TABLE IF EXISTS recipes;
DROP TABLE IF EXISTS ingredient_type;
DROP TABLE IF EXISTS ingredients;
DROP TABLE IF EXISTS instructions;
DROP TABLE IF EXISTS comments;
DROP TABLE IF EXISTS favourites;

CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  security_question TEXT NOT NULL,
  security_answer TEXT NOT NULL
);

CREATE TABLE recipes ( -- Recettes
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL,
    added TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    notes TEXT NOT NULL,
    author_grade INTEGER DEFAULT 0,
    prepTime INTEGER DEFAULT 0,
    cookTime INTEGER DEFAULT 0,
    servings INTEGER DEFAULT 0,
    difficulty INTEGER DEFAULT 0,
    image_url TEXT DEFAULT NULL,
    FOREIGN KEY (author_id) REFERENCES user (id)
);

CREATE TABLE ingredient_type (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  image_url TEXT 
);

CREATE TABLE ingredients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id INTEGER NOT NULL,
  ingredient_id INTEGER NOT NULL,
  quantity REAL NOT NULL,
  unit TEXT NOT NULL, -- g, ml, pieces of, teaspoons
  FOREIGN KEY (recipe_id) REFERENCES recipes (id),
  FOREIGN KEY (ingredient_id) REFERENCES ingredient_type (id)
);

CREATE TABLE instructions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id INTEGER NOT NULL,
  step INTEGER NOT NULL,
  instruction TEXT NOT NULL,
  FOREIGN KEY (recipe_id) REFERENCES recipes (id)
);

CREATE TABLE comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  comment TEXT NOT NULL,
  grade INTEGER NOT NULL,
  image_url TEXT DEFAULT NULL,
  FOREIGN KEY (author_id) REFERENCES user (id),
  FOREIGN KEY (recipe_id) REFERENCES recipes (id)
);

CREATE TABLE favourites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  author_id INTEGER NOT NULL,
  recipe_id INTEGER NOT NULL,
  FOREIGN KEY (author_id) REFERENCES user (id),
  FOREIGN KEY (recipe_id) REFERENCES recipes (id)
);