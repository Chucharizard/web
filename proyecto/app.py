from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy.orm import Session
from datetime import datetime
import pdfkit

app = Flask(__name__)
app.secret_key = 'clave_secreta'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sitio.db'
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'iniciar_sesion'

# Configuración de pdfkit
config = pdfkit.configuration(wkhtmltopdf='C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe')

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre_usuario = db.Column(db.String(150), unique=True, nullable=False)
    contraseña = db.Column(db.String(150), nullable=False)
    rol = db.Column(db.String(50), nullable=False)
    tarjeta = db.Column(db.String(20), nullable=True)  # Nuevo campo
    compras = db.relationship('Compra', backref='usuario', lazy=True)


class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    imagen = db.Column(db.String(20), nullable=False, default='default.jpg')

class Carrito(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)

class Compra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    total = db.Column(db.Float, nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False)
    detalles = db.relationship('DetalleCompra', backref='compra', lazy=True)

class DetalleCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    compra_id = db.Column(db.Integer, db.ForeignKey('compra.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio = db.Column(db.Float, nullable=False)

@login_manager.user_loader
def cargar_usuario(usuario_id):
    with Session(db.engine) as session:
        return session.get(Usuario, int(usuario_id))

@app.route('/')
def index():
    productos = Producto.query.all()
    return render_template('index.html', productos=productos)

@app.route('/iniciar_sesion', methods=['GET', 'POST'])
def iniciar_sesion():
    if request.method == 'POST':
        nombre_usuario = request.form['nombre_usuario']
        contraseña = request.form['contraseña']
        usuario = Usuario.query.filter_by(nombre_usuario=nombre_usuario).first()
        if usuario and usuario.contraseña == contraseña:
            login_user(usuario)
            session['carrito'] = []
            return redirect(url_for('index'))
        else:
            flash('Credenciales inválidas')
    return render_template('iniciar_sesion.html')

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        nombre_usuario = request.form['nombre_usuario']
        contraseña = request.form['contraseña']
        if Usuario.query.filter_by(nombre_usuario=nombre_usuario).first():
            flash('El nombre de usuario ya existe')
        else:
            usuario = Usuario(nombre_usuario=nombre_usuario, contraseña=contraseña, rol='usuario')
            db.session.add(usuario)
            db.session.commit()
            flash('Cuenta creada exitosamente')
            return redirect(url_for('iniciar_sesion'))
    return render_template('registrar.html')

@app.route('/cerrar_sesion')
@login_required
def cerrar_sesion():
    logout_user()
    session.pop('carrito', None)
    return redirect(url_for('index'))

@app.route('/agregar_al_carrito/<int:producto_id>', methods=['POST'])
@login_required
def agregar_al_carrito(producto_id):
    cantidad = int(request.form['cantidad'])
    producto = Producto.query.get(producto_id)
    if producto.cantidad < cantidad:
        flash('No hay suficiente stock disponible')
        return redirect(url_for('index'))
    carrito = session.get('carrito', [])
    for item in carrito:
        if item['producto_id'] == producto_id:
            item['cantidad'] += cantidad
            break
    else:
        carrito.append({'producto_id': producto_id, 'cantidad': cantidad})
    session['carrito'] = carrito
    return redirect(url_for('ver_carrito'))

@app.route('/carrito')
@login_required
def ver_carrito():
    carrito = session.get('carrito', [])
    productos_carrito = []
    total = 0
    for item in carrito:
        producto = Producto.query.get(item['producto_id'])
        productos_carrito.append({'producto': producto, 'cantidad': item['cantidad'], 'subtotal': producto.precio * item['cantidad']})
        total += producto.precio * item['cantidad']
    return render_template('carrito.html', productos_carrito=productos_carrito, total=total)

@app.route('/comprar', methods=['GET', 'POST'])
@login_required
def comprar():
    if request.method == 'POST':
        metodo_pago = request.form['metodo_pago']
        total_original = float(request.form['total'])
        if metodo_pago == 'efectivo':
            descuento = total_original * 0.05
            total = total_original - descuento  # 5% descuento
            incremento = 0  # inicializar incremento
        elif metodo_pago == 'tarjeta':
            incremento = total_original * 0.10
            total = total_original + incremento  # 10% incremento
            descuento = 0  # inicializar descuento
        else:
            descuento = 0
            incremento = 0
            total = total_original

        compra = Compra(usuario_id=current_user.id, total=total, metodo_pago=metodo_pago)
        db.session.add(compra)
        db.session.commit()

        carrito = session.get('carrito', [])
        for item in carrito:
            detalle = DetalleCompra(compra_id=compra.id, producto_id=item['producto_id'], cantidad=item['cantidad'], precio=Producto.query.get(item['producto_id']).precio)
            db.session.add(detalle)
            producto = Producto.query.get(item['producto_id'])
            producto.cantidad -= item['cantidad']
            db.session.commit()

        session['carrito'] = []
        return redirect(url_for('factura', compra_id=compra.id, descuento=descuento, incremento=incremento))
    return redirect(url_for('ver_carrito'))

@app.route('/factura/<int:compra_id>')
@login_required
def factura(compra_id):
    compra = Compra.query.get_or_404(compra_id)
    usuario = Usuario.query.get(compra.usuario_id)
    detalles = DetalleCompra.query.filter_by(compra_id=compra.id).all()
    productos_detalles = []
    for detalle in detalles:
        producto = Producto.query.get(detalle.producto_id)
        productos_detalles.append({'producto': producto, 'cantidad': detalle.cantidad, 'precio': detalle.precio})
    
    if compra.metodo_pago == 'efectivo':
        descuento = compra.total * 0.05 / 0.95
        incremento = 0
    elif compra.metodo_pago == 'tarjeta':
        incremento = compra.total * 0.10 / 1.10
        descuento = 0
    else:
        descuento = 0
        incremento = 0
    
    fecha_con_hora = compra.fecha.strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template('factura.html', compra=compra, productos_detalles=productos_detalles, descuento=descuento, incremento=incremento, fecha=fecha_con_hora, usuario=usuario.nombre_usuario)


@app.route('/descargar_factura/<int:compra_id>')
@login_required
def descargar_factura(compra_id):
    compra = Compra.query.get_or_404(compra_id)
    usuario = Usuario.query.get(compra.usuario_id)
    detalles = DetalleCompra.query.filter_by(compra_id=compra.id).all()
    productos_detalles = []
    for detalle in detalles:
        producto = Producto.query.get(detalle.producto_id)
        productos_detalles.append({'producto': producto, 'cantidad': detalle.cantidad, 'precio': detalle.precio})
    
    if compra.metodo_pago == 'efectivo':
        descuento = compra.total * 0.05 / 0.95
        incremento = 0
    elif compra.metodo_pago == 'tarjeta':
        incremento = compra.total * 0.10 / 1.10
        descuento = 0
    else:
        descuento = 0
        incremento = 0

    fecha_con_hora = compra.fecha.strftime('%Y-%m-%d %H:%M:%S')
    
    rendered = render_template('factura_pdf.html', compra=compra, productos_detalles=productos_detalles, descuento=descuento, incremento=incremento, fecha=fecha_con_hora, usuario=usuario.nombre_usuario)
    pdf = pdfkit.from_string(rendered, False, configuration=config)
    
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=factura_{compra.id}.pdf'
    return response





@app.route('/administrador')
@login_required
def administrador():
    if current_user.rol != 'admin':
        flash('Acceso denegado')
        return redirect(url_for('index'))
    productos = Producto.query.all()
    return render_template('administrador.html', productos=productos)

@app.route('/gestion_clientes')
@login_required
def gestion_clientes():
    if current_user.rol != 'admin':
        flash('Acceso denegado')
        return redirect(url_for('index'))
    usuarios = Usuario.query.all()
    datos_clientes = []
    for usuario in usuarios:
        compras = Compra.query.filter_by(usuario_id=usuario.id).all()
        cantidad_compras = len(compras)
        total_gastado = sum(compra.total for compra in compras)
        datos_clientes.append({'id': usuario.id, 'nombre_usuario': usuario.nombre_usuario, 'cantidad_compras': cantidad_compras, 'total_gastado': total_gastado})
    return render_template('gestion_clientes.html', datos_clientes=datos_clientes)


@app.route('/agregar_producto', methods=['GET', 'POST'])
@login_required
def agregar_producto():
    if request.method == 'POST':
        nombre = request.form['nombre']
        precio = request.form['precio']
        cantidad = request.form['cantidad']
        imagen = 'default.jpg'
        if 'pan' in nombre.lower():
            imagen = 'pan.jpg'
        elif 'leche' in nombre.lower():
            imagen = 'leche.jpg'
        elif 'huevos' in nombre.lower():
            imagen = 'huevos.jpg'
        elif 'coca' in nombre.lower():
            imagen = 'coca.jpg'
        elif 'manzana' in nombre.lower():
            imagen = 'manzana.jpg'
        elif 'platano' in nombre.lower():  
            imagen = 'platano.jpg'
        # Añadir más condiciones para otras imágenes aquí
        nuevo_producto = Producto(nombre=nombre, precio=precio, cantidad=cantidad, imagen=imagen)
        db.session.add(nuevo_producto)
        db.session.commit()
        return redirect(url_for('administrador'))
    return render_template('agregar_producto.html')

@app.route('/actualizar_producto/<int:producto_id>', methods=['GET', 'POST'])
@login_required
def actualizar_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    if request.method == 'POST':
        producto.nombre = request.form['nombre']
        producto.precio = request.form['precio']
        producto.cantidad = request.form['cantidad']
        producto.imagen = 'default.jpg'
        if 'pan' in producto.nombre.lower():
            producto.imagen = 'pan.jpg'
        elif 'leche' in producto.nombre.lower():
            producto.imagen = 'leche.jpg'
        elif 'huevos' in producto.nombre.lower():
            producto.imagen = 'huevos.jpg'
        elif 'coca' in producto.nombre.lower():
            producto.imagen = 'coca.jpg'
        elif 'manzana' in producto.nombre.lower():
            producto.imagen = 'manzana.jpg'
        elif 'platano' in producto.nombre.lower():  
            producto.imagen = 'platano.jpg'
        # Añadir más condiciones para otras imágenes aquí
        db.session.commit()
        return redirect(url_for('administrador'))
    return render_template('actualizar_producto.html', producto=producto)

@app.route('/eliminar_producto/<int:producto_id>', methods=['POST'])
@login_required
def eliminar_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    db.session.delete(producto)
    db.session.commit()
    return redirect(url_for('administrador'))


@app.route('/detalle_cliente/<int:usuario_id>')
@login_required
def detalle_cliente(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    compras = Compra.query.filter_by(usuario_id=usuario_id).all()
    compras_detalles = []
    
    for compra in compras:
        detalles = DetalleCompra.query.filter_by(compra_id=compra.id).all()
        detalles_con_productos = []
        for detalle in detalles:
            producto = Producto.query.get(detalle.producto_id)
            detalles_con_productos.append({
                'cantidad': detalle.cantidad,
                'producto': producto,
                'precio': detalle.precio
            })
        compra_info = {
            'fecha': compra.fecha,
            'total': compra.total,
            'detalles': detalles_con_productos
        }
        compras_detalles.append(compra_info)
    
    return render_template('detalle_cliente.html', usuario=usuario, compras=compras_detalles)






if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Crear usuario predeterminado si no existe
        if not Usuario.query.filter_by(nombre_usuario='pan').first():
            usuario = Usuario(nombre_usuario='pan', contraseña='123', rol='admin')
            db.session.add(usuario)
            db.session.commit()
    app.run(debug=True)

