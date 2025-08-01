from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from sqlalchemy.exc import SQLAlchemyError
from src.models import db
from src.models.user import User
from src.models.item import Item
from src.models.supplier import Supplier
from src.models.location import Zone, Furniture, Drawer
import os
import sys

# Ajouter le répertoire parent au chemin de recherche pour les importations
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.database import save_config as save_db_config, get_postgres_config_values, DB_TYPE
from config.app_config import get_app_config_values, save_app_config_value

# Note: La classe ItemTempo n'est plus utilisée après la refactorisation

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/db-config', methods=['GET', 'POST'])
def db_config():
    """
    Configuration de la base de données
    """
    if 'user_id' not in session:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        host = request.form.get('host')
        database = request.form.get('database')
        user = request.form.get('user')
        password = request.form.get('password')
        port = request.form.get('port')
        
        if host and database and user and password and port:
            try:
                # Sauvegarder la nouvelle configuration
                save_db_config(host, database, user, password, port)
                
                # Notifier l'utilisateur du changement
                flash('Configuration de la base de données PostgreSQL mise à jour. Un redémarrage de l''application est nécessaire pour appliquer les changements.', 'success')
                return redirect(url_for('admin.db_config'))
            except Exception as e:
                flash(f'Erreur lors de la mise à jour de la configuration: {str(e)}', 'error')
        else:
            flash('Tous les champs sont obligatoires', 'error')
    
    # Récupérer la configuration actuelle et déterminer le message d'information spécifique à la page pour les requêtes GET
    current_config = {}
    db_type_in_use = DB_TYPE
    page_info_message = None
    page_info_category = None

    if db_type_in_use == 'postgresql':
        current_config = get_postgres_config_values()
        if request.method == 'GET':
            page_info_message = 'Le formulaire ci-dessous permet de modifier la configuration de PostgreSQL. Un redémarrage est requis pour appliquer les changements.'
            page_info_category = 'info'
    elif db_type_in_use == 'sqlite':
        current_config = {'message': 'SQLite est actuellement utilisé. La configuration se fait via les variables d''environnement (.env).'}
        if request.method == 'GET':
            page_info_message = 'SQLite est actif. La configuration de la base de données se fait via les variables d''environnement dans le fichier .env. Ce formulaire est désactivé.'
            page_info_category = 'warning'
    else:
        current_config = {'message': f'Type de base de données inconnu: {db_type_in_use}'}
        if request.method == 'GET':
            page_info_message = f'Type de base de données non reconnu: {db_type_in_use}. Vérifiez la variable DB_TYPE dans votre fichier .env.'
            page_info_category = 'danger'

    return render_template('admin/db_config.html', 
                           config=current_config, 
                           db_type=db_type_in_use,
                           page_info_message=page_info_message,
                           page_info_category=page_info_category)


@admin_bp.route('/app-config', methods=['GET', 'POST'])
def app_config():
    """
    Configuration de l'application (ex: Clé API OpenAI).
    """
    if 'user_id' not in session:
        return redirect(url_for('main.index'))

    page_info_message = None
    page_info_category = None

    if request.method == 'POST':
        openai_api_key_from_form = request.form.get('OPENAI_API_KEY')

        if openai_api_key_from_form: # Sauvegarder seulement si une nouvelle clé est entrée
            if save_app_config_value('OPENAI_API_KEY', openai_api_key_from_form):
                flash('Clé API OpenAI mise à jour avec succès. Un redémarrage de l\'application peut être nécessaire.', 'success')
            else:
                flash('Erreur lors de la mise à jour de la clé API OpenAI.', 'error')
        else:
            flash('Le champ de la clé API OpenAI était vide. Aucune modification apportée à cette clé.', 'info')
        
        # Gérer d'autres clés de configuration ici si nécessaire à l'avenir
        return redirect(url_for('admin.app_config'))

    # Pour les requêtes GET
    current_app_config = get_app_config_values()
    
    config_for_template = {}
    for key, value in current_app_config.items():
        if value: 
            config_for_template[key] = "Configurée"
        else:
            config_for_template[key] = "Non configurée"

    if request.method == 'GET':
        page_info_message = "Gérez ici les configurations globales de l'application, comme les clés API. Les modifications peuvent nécessiter un redémarrage de l'application."
        page_info_category = 'info'
        
    return render_template('admin/app_config.html',
                           config=config_for_template, 
                           page_info_message=page_info_message,
                           page_info_category=page_info_category)

# Route principale d'administration - redirige vers la liste des articles
@admin_bp.route('/')
def admin_dashboard():
    return redirect(url_for('admin.items_list'))

# Gestion des utilisateurs
@admin_bp.route('/users')
def user_list():
    users = db.session.query(User).order_by(User.name).all()
    
    return render_template('admin/user_list.html', users=users)

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    try:
        user = db.session.get(User, user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            flash("Utilisateur supprimé avec succès.", "success")
        else:
            flash("Utilisateur non trouvé.", "danger")
        
        return redirect(url_for('admin.user_list'))
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la suppression de l'utilisateur: {str(e)}", "danger")
        return redirect(url_for('admin.user_list'))

# Gestion des articles
@admin_bp.route('/items')
def items_list():
    # Récupérer le paramètre de filtre s'il existe
    filter_type = request.args.get('filter', 'all')  # Par défaut : afficher tous les articles
    search_term = request.args.get('search', '').strip()
    
    # Construire la requête de base
    query = db.session.query(Item)
    
    # Appliquer le filtre si nécessaire
    if filter_type == 'temporary':
        query = query.filter(Item.is_temporary == True)
    elif filter_type == 'conventional':
        query = query.filter(Item.is_temporary == False)

    # Appliquer le filtre de recherche si un terme est fourni
    if search_term:
        query = query.filter(Item.name.ilike(f'%{search_term}%'))
    
    # Trier les résultats par nom
    items = query.order_by(Item.name).all()
    
    items_list = []
    for item in items:
        
        # Créer un dictionnaire avec les informations de l'article
        item_dict = {
            'id': item.id,
            'name': item.name,
            'quantity': item.quantity,
            'is_temporary': item.is_temporary,
            'supplier': item.supplier_rel.name if item.supplier_rel else 'Non spécifié',
        }
        
        # Ajouter les informations de localisation pour les articles non temporaires
        if not item.is_temporary:
            item_dict.update({
                'zone_name': item.zone_rel.name if item.zone_rel else 'Non spécifié',
                'furniture_name': item.furniture_rel.name if item.furniture_rel else 'Non spécifié',
                'drawer_name': item.drawer_rel.name if item.drawer_rel else 'Non spécifié'
            })
        else:
            item_dict.update({
                'zone_name': 'N/A',
                'furniture_name': 'N/A',
                'drawer_name': 'N/A'
            })
        
        items_list.append(item_dict)
    
    return render_template('admin/items_list.html', 
                           items=items_list, 
                           current_filter=filter_type,
                           items_count=len(items_list),
                           search_term=search_term)  # Passer le terme de recherche au template

@admin_bp.route('/add-item', methods=['GET', 'POST'])
def add_item():
    zones_query = db.session.query(Zone).order_by(Zone.name).all()
    furnitures_query = db.session.query(Furniture).order_by(Furniture.name).all()
    drawers_query = db.session.query(Drawer).order_by(Drawer.name).all()
    suppliers_query = db.session.query(Supplier).order_by(Supplier.name).all()

    # form_data = {'name': '', 'selected_zone': None, 'selected_furniture': None, 'selected_drawer': None}
    form_data = {'name': '', 'selected_zone': None, 'selected_furniture': None, 'selected_drawer': None, 'selected_supplier': None}

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        quantity = request.form.get('quantity', '1').strip() or '1'
        supplier_id_str = request.form.get('supplier_id')
        zone_id_str = request.form.get('zone_id')
        furniture_id_str = request.form.get('furniture_id')
        drawer_id_str = request.form.get('drawer_id')

        form_data['name'] = name
        try:
            form_data['selected_zone'] = int(zone_id_str) if zone_id_str else None
        except ValueError:
            form_data['selected_zone'] = None
        try:
            form_data['selected_furniture'] = int(furniture_id_str) if furniture_id_str else None
        except ValueError:
            form_data['selected_furniture'] = None
        try:
            form_data['selected_drawer'] = int(drawer_id_str) if drawer_id_str else None
        except ValueError:
            form_data['selected_drawer'] = None
        try:
            form_data['selected_supplier'] = int(supplier_id_str) if supplier_id_str else None
        except ValueError:
            form_data['selected_supplier'] = None


        if not name:
            flash("Le nom de l'article est requis.", "danger")
            return render_template('admin/add_item.html', zones=zones_query, furnitures=furnitures_query, drawers=drawers_query, suppliers=suppliers_query, **form_data)

        if not zone_id_str or not furniture_id_str or not drawer_id_str or not supplier_id_str:
            flash("Toutes les informations (Fournisseur, Zone, Mobilier, Tiroir) sont requises.", "danger")
            return render_template('admin/add_item.html', zones=zones_query, furnitures=furnitures_query, drawers=drawers_query, suppliers=suppliers_query, **form_data)

        try:
            zone_id = int(zone_id_str)
            furniture_id = int(furniture_id_str)
            drawer_id = int(drawer_id_str)
            supplier_id = int(supplier_id_str)
            form_data['selected_zone'] = zone_id
            form_data['selected_furniture'] = furniture_id
            form_data['selected_drawer'] = drawer_id
            form_data['selected_supplier'] = supplier_id
        except ValueError:
            flash("Les identifiants doivent être des nombres valides.", "danger")
            return render_template('admin/add_item.html', zones=zones_query, furnitures=furnitures_query, drawers=drawers_query, suppliers=suppliers_query, **form_data)

        try:
            existing_item = Item.query.filter_by(
                name=name,
                supplier_id=supplier_id,
                zone_id=zone_id,
                furniture_id=furniture_id,
                drawer_id=drawer_id,
                is_temporary=False
            ).first()

            if existing_item:
                flash(f"Un article conventionnel nommé '{name}' existe déjà à cet emplacement exact avec ce fournisseur.", "warning")
                return render_template('admin/add_item.html', zones=zones_query, furnitures=furnitures_query, drawers=drawers_query, suppliers=suppliers_query, **form_data)

            new_item = Item(
                name=name,
                supplier_id=supplier_id,
                zone_id=zone_id,
                furniture_id=furniture_id,
                drawer_id=drawer_id,
                is_temporary=False
            )
            db.session.add(new_item)
            db.session.commit()

            flash("Article ajouté avec succès.", "success")
            return redirect(url_for('admin.items_list'))

        except SQLAlchemyError as e:
            db.session.rollback()
            flash(f"Erreur de base de données lors de l'ajout de l'article: {str(e)}", "danger")
            return render_template('admin/add_item.html', zones=zones_query, furnitures=furnitures_query, drawers=drawers_query, suppliers=suppliers_query, **form_data)
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur inattendue lors de l'ajout de l'article: {str(e)}", "danger")
            return render_template('admin/add_item.html', zones=zones_query, furnitures=furnitures_query, drawers=drawers_query, suppliers=suppliers_query, **form_data)

    return render_template('admin/add_item.html', zones=zones_query, furnitures=furnitures_query, drawers=drawers_query, suppliers=suppliers_query, **form_data)

@admin_bp.route('/edit-item/<int:item_id>', methods=['GET', 'POST'])
def edit_item(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        flash("Article non trouvé.", "danger")
        return redirect(url_for('admin.items_list'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        quantity = request.form.get('quantity', '1').strip()
        supplier_id_str = request.form.get('supplier_id')
        zone_id_str = request.form.get('zone_id')
        furniture_id_str = request.form.get('furniture_id')
        drawer_id_str = request.form.get('drawer_id')

        if not name or not supplier_id_str or not zone_id_str or not furniture_id_str or not drawer_id_str or not quantity:
            flash("Tous les champs sont requis.", "danger")
            return redirect(url_for('admin.edit_item', item_id=item_id))

        try:
            item.name = name
            item.quantity = int(quantity)
            item.supplier_id = int(supplier_id_str)
            item.zone_id = int(zone_id_str)
            item.furniture_id = int(furniture_id_str)
            item.drawer_id = int(drawer_id_str)
            db.session.commit()
            flash("Article modifié avec succès.", "success")
            return redirect(url_for('admin.items_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur lors de la modification de l'article: {str(e)}", "danger")
            return redirect(url_for('admin.edit_item', item_id=item_id))
    
    # GET request - afficher le formulaire
    zones = db.session.query(Zone).order_by(Zone.name).all()
    furnitures = db.session.query(Furniture).order_by(Furniture.name).all()
    drawers = db.session.query(Drawer).order_by(Drawer.name).all()
    suppliers = db.session.query(Supplier).order_by(Supplier.name).all()
    
    return render_template('admin/edit_item.html', item=item, zones=zones, furnitures=furnitures, drawers=drawers, suppliers=suppliers)

@admin_bp.route('/items/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    try:
        item = db.session.get(Item, item_id)
        if not item:
            return jsonify(success=False, error="Article non trouvé."), 404
        
        item_name = item.name # Sauvegarder le nom avant la suppression
        db.session.delete(item)
        db.session.commit()
        return jsonify(success=True, message=f"Article '{item_name}' supprimé avec succès.")

    except SQLAlchemyError as e: # Être plus spécifique sur l'exception si possible
        db.session.rollback()
        # Log l'erreur pour le débogage côté serveur
        # current_app.logger.error(f"SQLAlchemyError lors de la suppression de l'article {item_id}: {str(e)}")
        return jsonify(success=False, error="Erreur de base de données lors de la suppression."), 500
    except Exception as e:
        db.session.rollback()
        # Log l'erreur pour le débogage côté serveur
        # current_app.logger.error(f"Erreur générique lors de la suppression de l'article {item_id}: {str(e)}")
        return jsonify(success=False, error=f"Une erreur est survenue: {str(e)}"), 500

@admin_bp.route('/items/delete-temporary', methods=['POST'])
def delete_temporary_items():
    try:
        # Sélectionner les articles temporaires qui ne sont PAS dans la liste des empruntés
        items_to_delete = db.session.query(Item).filter(
            Item.is_temporary == True,
        ).all()
        
        count_deleted = len(items_to_delete)

        if not items_to_delete:
            return jsonify(success=True, message="Aucun article temporaire à supprimer.", count=0)

        for item in items_to_delete:
            db.session.delete(item)
        
        db.session.commit()
        return jsonify(success=True, message=f"{count_deleted} article(s) temporaire(s) ont été supprimé(s).", count=count_deleted)

    except SQLAlchemyError as e:
        db.session.rollback()
        # current_app.logger.error(f"SQLAlchemyError lors de la suppression des articles temporaires: {str(e)}")
        return jsonify(success=False, error="Erreur de base de données lors de la suppression des articles temporaires."), 500
    except Exception as e:
        db.session.rollback()
        # current_app.logger.error(f"Erreur générique lors de la suppression des articles temporaires: {str(e)}")
        return jsonify(success=False, error=f"Une erreur est survenue: {str(e)}"), 500

# Gestion des emplacements
@admin_bp.route('/locations')
def location_admin():
    """
    Page d'administration des emplacements
    """
    zones = db.session.query(Zone).order_by(Zone.name).all()
    furnitures = db.session.query(Furniture).order_by(Furniture.name).all()
    drawers = db.session.query(Drawer).order_by(Drawer.name).all()
    return render_template('admin/location.html', zones=zones, furnitures=furnitures, drawers=drawers)

# Reconnaissance vocale d'inventaire
@admin_bp.route('/inventory-voice')
def inventory_voice_admin():
    """
    Page d'administration pour la reconnaissance vocale d'inventaire
    """
    return render_template('admin/inventory_voice.html')

@admin_bp.route('/quantity-update-confirmation')
def quantity_update_confirmation():
    item_id = request.args.get('item_id', type=int)
    new_quantity = request.args.get('new_quantity', type=int)
    old_quantity = request.args.get('old_quantity', type=int)
    action_text = request.args.get('action_text', '')

    item = db.session.get(Item, item_id)
    if not item:
        flash("Article non trouvé.", "danger")
        return redirect(url_for('admin.items_list'))

    return render_template('admin/quantity_update_confirmation.html',
                           item_id=item.id,
                           item_name=item.name,
                           new_quantity=new_quantity,
                           old_quantity=old_quantity,
                           action_text=action_text)

@admin_bp.route('/confirm-quantity-update', methods=['POST'])
def confirm_quantity_update():
    item_id = request.form.get('item_id', type=int)
    new_quantity = request.form.get('new_quantity', type=int)

    item = db.session.get(Item, item_id)
    if not item:
        flash("Article non trouvé.", "danger")
        return redirect(url_for('admin.items_list'))

    try:
        item.quantity = new_quantity
        db.session.commit()
        flash(f"La quantité de '{item.name}' a été mise à jour avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la mise à jour de la quantité : {str(e)}", "danger")

    return redirect(url_for('admin.items_list'))
