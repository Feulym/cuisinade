import os
import uuid
from werkzeug.utils import secure_filename
from PIL import Image
from app import UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_SIZE = (1024, 1024)  # Taille maximale pour optimisation

def allowed_file(filename):
    """Vérifie si le fichier est autorisé"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file, upload_folder, optimize=True):
    """
    Sauvegarde une image avec un nom unique
    
    Args:
        file: Le fichier uploadé (FileStorage)
        upload_folder: Dossier de destination (ex: 'recipes' ou 'comments')
        optimize: Si True, optimise et redimensionne l'image
    
    Returns:
        str: Chemin relatif de l'image sauvegardée ou None si erreur
    """
    if file and allowed_file(file.filename):
        # Générer un nom unique
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4()}.{ext}"
        
        # Chemin complet
        folder_path = os.path.join('app', UPLOAD_FOLDER, upload_folder)
        os.makedirs(folder_path, exist_ok=True)
        filepath = os.path.join(folder_path, filename)
        
        if optimize:
            try:
                # Ouvrir l'image avec Pillow
                img = Image.open(file)
                
                # Convertir en RGB si nécessaire (pour les PNG avec transparence)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Redimensionner si trop grand
                img.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
                
                # Sauvegarder avec compression
                img.save(filepath, optimize=True, quality=85)
                
            except Exception as e:
                print(f"Erreur lors de l'optimisation de l'image: {e}")
                # Sauvegarder sans optimisation en cas d'erreur
                file.seek(0)
                file.save(filepath)
        else:
            file.save(filepath)
        
        # Retourner le chemin relatif pour la base de données
        return f"../{UPLOAD_FOLDER}/{upload_folder}/{filename}"
    
    return None

def delete_image(image_url):
    """Supprime une image du serveur"""
    filepath = image_url.replace('../', 'app/')
    if filepath:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception as e:
            print(f"Erreur lors de la suppression de l'image: {e}")
    return False