from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3, os, hashlib
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'servisucre_clave_secreta_2025'

UPLOAD_FOLDER  = 'static/uploads'
GALERIA_FOLDER = 'static/galeria'
ALLOWED_EXT    = {'png', 'jpg', 'jpeg', 'webp'}
ADMIN_USER     = 'admin'
ADMIN_PASS     = hashlib.sha256('servisucre2025'.encode()).hexdigest()

app.config['UPLOAD_FOLDER']  = UPLOAD_FOLDER
app.config['GALERIA_FOLDER'] = GALERIA_FOLDER

# ============================================================
# HELPERS
# ============================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_calificacion(proveedor_id):
    conn = get_db()
    r = conn.execute('SELECT AVG(estrellas), COUNT(*) FROM calificaciones WHERE proveedor_id=?',
                     (proveedor_id,)).fetchone()
    conn.close()
    return (round(r[0], 1) if r[0] else 0), r[1]

def get_reportes_count(proveedor_id):
    conn = get_db()
    r = conn.execute('SELECT COUNT(*) FROM reportes WHERE proveedor_id=? AND resuelto=0',
                     (proveedor_id,)).fetchone()
    conn.close()
    return r[0]

def get_proveedor_dict(p):
    promedio, total = get_calificacion(p['id'])
    reportes        = get_reportes_count(p['id'])
    return {
        'id':          p['id'],
        'nombre':      p['nombre'],
        'servicio':    p['servicio'],
        'barrio':      p['barrio'],
        'telefono':    p['telefono'],
        'descripcion': p['descripcion'],
        'foto':        p['foto'],
        'promedio':    promedio,
        'total':       total,
        'reportes':    reportes
    }

# ============================================================
# BASE DE DATOS
# ============================================================
def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS proveedores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT NOT NULL,
            servicio    TEXT NOT NULL,
            barrio      TEXT NOT NULL,
            telefono    TEXT NOT NULL,
            descripcion TEXT,
            foto        TEXT,
            password    TEXT NOT NULL,
            activo      INTEGER DEFAULT 1,
            fecha_reg   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS calificaciones (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER NOT NULL,
            estrellas    INTEGER NOT NULL,
            comentario   TEXT,
            autor        TEXT,
            fecha        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
        );

        CREATE TABLE IF NOT EXISTS servicios_adicionales (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER NOT NULL,
            servicio     TEXT NOT NULL,
            descripcion  TEXT,
            FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
        );

        CREATE TABLE IF NOT EXISTS galeria (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER NOT NULL,
            filename     TEXT NOT NULL,
            descripcion  TEXT,
            fecha        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
        );

        CREATE TABLE IF NOT EXISTS reportes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor_id INTEGER NOT NULL,
            motivo       TEXT NOT NULL,
            descripcion  TEXT,
            reporter_ip  TEXT,
            resuelto     INTEGER DEFAULT 0,
            fecha        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
        );
    ''')
    conn.commit()
    conn.close()
    os.makedirs(UPLOAD_FOLDER,  exist_ok=True)
    os.makedirs(GALERIA_FOLDER, exist_ok=True)

# ============================================================
# RUTAS PÚBLICAS
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/buscar')
def buscar():
    query  = request.args.get('q', '')
    barrio = request.args.get('barrio', '')
    orden  = request.args.get('orden', 'reciente')
    conn   = get_db()

    if query and barrio:
        rows = conn.execute('''
            SELECT DISTINCT p.* FROM proveedores p
            LEFT JOIN servicios_adicionales sa ON sa.proveedor_id = p.id
            WHERE p.activo=1 AND (p.servicio LIKE ? OR sa.servicio LIKE ?)
            AND p.barrio LIKE ?''',
            (f'%{query}%', f'%{query}%', f'%{barrio}%')).fetchall()
    elif query:
        rows = conn.execute('''
            SELECT DISTINCT p.* FROM proveedores p
            LEFT JOIN servicios_adicionales sa ON sa.proveedor_id = p.id
            WHERE p.activo=1 AND (p.servicio LIKE ? OR sa.servicio LIKE ?)''',
            (f'%{query}%', f'%{query}%')).fetchall()
    elif barrio:
        rows = conn.execute('SELECT * FROM proveedores WHERE activo=1 AND barrio LIKE ?',
                            (f'%{barrio}%',)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM proveedores WHERE activo=1').fetchall()
    conn.close()

    proveedores = [get_proveedor_dict(p) for p in rows]

    if orden == 'calificacion':
        proveedores.sort(key=lambda x: x['promedio'], reverse=True)
    elif orden == 'resenas':
        proveedores.sort(key=lambda x: x['total'], reverse=True)

    return render_template('buscar.html', proveedores=proveedores,
                           query=query, barrio=barrio, orden=orden)

@app.route('/perfil/<int:pid>')
def perfil(pid):
    conn = get_db()
    p = conn.execute('SELECT * FROM proveedores WHERE id=?', (pid,)).fetchone()
    if not p:
        conn.close(); return redirect('/buscar')

    reviews  = conn.execute('''SELECT estrellas, comentario, autor, fecha
                                FROM calificaciones WHERE proveedor_id=?
                                ORDER BY fecha DESC''', (pid,)).fetchall()
    s_extra  = conn.execute('''SELECT id, servicio, descripcion
                                FROM servicios_adicionales WHERE proveedor_id=?''',
                             (pid,)).fetchall()
    galeria  = conn.execute('''SELECT id, filename, descripcion
                                FROM galeria WHERE proveedor_id=?
                                ORDER BY fecha DESC''', (pid,)).fetchall()
    conn.close()

    proveedor = get_proveedor_dict(p)
    es_dueno  = session.get('proveedor_id') == pid
    return render_template('perfil.html', proveedor=proveedor,
                           reviews=reviews, servicios_extra=s_extra,
                           galeria=galeria, es_dueno=es_dueno)

# ============================================================
# REGISTRO / LOGIN / LOGOUT
# ============================================================
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    error = None
    if request.method == 'POST':
        pw  = request.form['password']
        pw2 = request.form['confirmar']
        if pw != pw2:
            error = 'Las contraseñas no coinciden'
        elif len(pw) < 6:
            error = 'La contraseña debe tener al menos 6 caracteres'
        else:
            conn = get_db()
            cur  = conn.execute('''
                INSERT INTO proveedores (nombre,servicio,barrio,telefono,descripcion,password)
                VALUES (?,?,?,?,?,?)''',
                (request.form['nombre'], request.form['servicio'],
                 request.form['barrio'],  request.form['telefono'],
                 request.form['descripcion'], hash_password(pw)))
            nuevo_id = cur.lastrowid
            conn.commit(); conn.close()
            session['proveedor_id'] = nuevo_id
            return redirect(f'/perfil/{nuevo_id}')
    return render_template('registro.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        p = get_db().execute(
            'SELECT id FROM proveedores WHERE telefono=? AND password=? AND activo=1',
            (request.form['telefono'], hash_password(request.form['password']))
        ).fetchone()
        if p:
            session['proveedor_id'] = p['id']
            return redirect(f'/perfil/{p["id"]}')
        error = 'Teléfono o contraseña incorrectos'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ============================================================
# EDITAR PERFIL
# ============================================================
@app.route('/perfil/<int:pid>/editar', methods=['GET', 'POST'])
def editar_perfil(pid):
    if session.get('proveedor_id') != pid:
        return redirect(f'/perfil/{pid}')

    conn = get_db()
    p    = conn.execute('SELECT * FROM proveedores WHERE id=?', (pid,)).fetchone()

    if request.method == 'POST':
        nueva_pw = request.form.get('password', '').strip()
        if nueva_pw:
            if nueva_pw != request.form.get('confirmar', ''):
                conn.close()
                return render_template('editar.html', proveedor=p,
                                       error='Las contraseñas no coinciden')
            conn.execute('''UPDATE proveedores SET nombre=?,servicio=?,barrio=?,
                            telefono=?,descripcion=?,password=? WHERE id=?''',
                         (request.form['nombre'], request.form['servicio'],
                          request.form['barrio'],  request.form['telefono'],
                          request.form['descripcion'], hash_password(nueva_pw), pid))
        else:
            conn.execute('''UPDATE proveedores SET nombre=?,servicio=?,barrio=?,
                            telefono=?,descripcion=? WHERE id=?''',
                         (request.form['nombre'], request.form['servicio'],
                          request.form['barrio'],  request.form['telefono'],
                          request.form['descripcion'], pid))
        conn.commit(); conn.close()
        return redirect(f'/perfil/{pid}')

    conn.close()
    return render_template('editar.html', proveedor=p, error=None)

# ============================================================
# FOTO DE PERFIL
# ============================================================
@app.route('/perfil/<int:pid>/subir-foto', methods=['POST'])
def subir_foto(pid):
    if session.get('proveedor_id') != pid:
        return redirect(f'/perfil/{pid}')
    file = request.files.get('foto')
    if file and allowed_file(file.filename):
        fn = secure_filename(f'perfil_{pid}_{file.filename}')
        file.save(os.path.join(UPLOAD_FOLDER, fn))
        conn = get_db()
        conn.execute('UPDATE proveedores SET foto=? WHERE id=?', (fn, pid))
        conn.commit(); conn.close()
    return redirect(f'/perfil/{pid}')

# ============================================================
# GALERÍA
# ============================================================
@app.route('/perfil/<int:pid>/galeria/subir', methods=['POST'])
def subir_galeria(pid):
    if session.get('proveedor_id') != pid:
        return redirect(f'/perfil/{pid}')

    conn  = get_db()
    total = conn.execute('SELECT COUNT(*) FROM galeria WHERE proveedor_id=?',
                         (pid,)).fetchone()[0]
    if total >= 6:
        conn.close()
        return redirect(f'/perfil/{pid}')

    file = request.files.get('foto')
    if file and allowed_file(file.filename):
        fn  = secure_filename(f'galeria_{pid}_{file.filename}')
        file.save(os.path.join(GALERIA_FOLDER, fn))
        conn.execute('INSERT INTO galeria (proveedor_id, filename, descripcion) VALUES (?,?,?)',
                     (pid, fn, request.form.get('descripcion', '')))
        conn.commit()
    conn.close()
    return redirect(f'/perfil/{pid}')

@app.route('/perfil/<int:pid>/galeria/eliminar/<int:foto_id>')
def eliminar_galeria(pid, foto_id):
    if session.get('proveedor_id') != pid:
        return redirect(f'/perfil/{pid}')
    conn = get_db()
    foto = conn.execute('SELECT filename FROM galeria WHERE id=? AND proveedor_id=?',
                        (foto_id, pid)).fetchone()
    if foto:
        ruta = os.path.join(GALERIA_FOLDER, foto['filename'])
        if os.path.exists(ruta): os.remove(ruta)
        conn.execute('DELETE FROM galeria WHERE id=?', (foto_id,))
        conn.commit()
    conn.close()
    return redirect(f'/perfil/{pid}')

# ============================================================
# SERVICIOS ADICIONALES
# ============================================================
@app.route('/perfil/<int:pid>/agregar-servicio', methods=['POST'])
def agregar_servicio(pid):
    if session.get('proveedor_id') != pid:
        return redirect(f'/perfil/{pid}')
    conn = get_db()
    conn.execute('INSERT INTO servicios_adicionales (proveedor_id,servicio,descripcion) VALUES (?,?,?)',
                 (pid, request.form['servicio'], request.form.get('descripcion','')))
    conn.commit(); conn.close()
    return redirect(f'/perfil/{pid}')

@app.route('/perfil/<int:pid>/eliminar-servicio/<int:sid>')
def eliminar_servicio(pid, sid):
    if session.get('proveedor_id') != pid:
        return redirect(f'/perfil/{pid}')
    conn = get_db()
    conn.execute('DELETE FROM servicios_adicionales WHERE id=? AND proveedor_id=?', (sid, pid))
    conn.commit(); conn.close()
    return redirect(f'/perfil/{pid}')

# ============================================================
# CALIFICACIONES
# ============================================================
@app.route('/calificar/<int:pid>', methods=['GET', 'POST'])
def calificar(pid):
    if request.method == 'POST':
        conn = get_db()
        conn.execute('''INSERT INTO calificaciones (proveedor_id,estrellas,comentario,autor)
                        VALUES (?,?,?,?)''',
                     (pid, int(request.form['estrellas']),
                      request.form.get('comentario',''),
                      request.form.get('autor','') or 'Anónimo'))
        conn.commit(); conn.close()
        return redirect(f'/perfil/{pid}')
    return render_template('calificar.html', proveedor_id=pid)

# ============================================================
# REPORTES
# ============================================================
@app.route('/reportar/<int:pid>', methods=['GET', 'POST'])
def reportar(pid):
    conn = get_db()
    p    = conn.execute('SELECT nombre FROM proveedores WHERE id=?', (pid,)).fetchone()
    if not p:
        conn.close(); return redirect('/buscar')

    if request.method == 'POST':
        conn.execute('''INSERT INTO reportes (proveedor_id, motivo, descripcion, reporter_ip)
                        VALUES (?,?,?,?)''',
                     (pid, request.form['motivo'],
                      request.form.get('descripcion',''),
                      request.remote_addr))
        conn.commit(); conn.close()
        return render_template('reporte_enviado.html', nombre=p['nombre'], pid=pid)

    conn.close()
    return render_template('reportar.html', proveedor_id=pid, nombre=p['nombre'])

# ============================================================
# PANEL ADMINISTRADOR
# ============================================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        if (request.form['usuario'] == ADMIN_USER and
                hash_password(request.form['password']) == ADMIN_PASS):
            session['admin'] = True
            return redirect('/admin')
        error = 'Credenciales incorrectas'
    return render_template('admin/login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin/login')

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect('/admin/login')
    conn = get_db()
    stats = {
        'total_proveedores': conn.execute('SELECT COUNT(*) FROM proveedores').fetchone()[0],
        'activos':           conn.execute('SELECT COUNT(*) FROM proveedores WHERE activo=1').fetchone()[0],
        'suspendidos':       conn.execute('SELECT COUNT(*) FROM proveedores WHERE activo=0').fetchone()[0],
        'total_resenas':     conn.execute('SELECT COUNT(*) FROM calificaciones').fetchone()[0],
        'reportes_nuevos':   conn.execute('SELECT COUNT(*) FROM reportes WHERE resuelto=0').fetchone()[0],
    }
    proveedores = conn.execute('''
        SELECT p.*, 
               COUNT(DISTINCT r.id) as num_reportes,
               AVG(c.estrellas)     as promedio
        FROM proveedores p
        LEFT JOIN reportes      r ON r.proveedor_id = p.id AND r.resuelto = 0
        LEFT JOIN calificaciones c ON c.proveedor_id = p.id
        GROUP BY p.id
        ORDER BY num_reportes DESC, p.fecha_reg DESC
    ''').fetchall()
    conn.close()
    return render_template('admin/dashboard.html', stats=stats, proveedores=proveedores)

@app.route('/admin/reportes')
def admin_reportes():
    if not session.get('admin'):
        return redirect('/admin/login')
    conn     = get_db()
    reportes = conn.execute('''
        SELECT r.*, p.nombre as proveedor_nombre
        FROM reportes r
        JOIN proveedores p ON p.id = r.proveedor_id
        WHERE r.resuelto = 0
        ORDER BY r.fecha DESC
    ''').fetchall()
    conn.close()
    return render_template('admin/reportes.html', reportes=reportes)

@app.route('/admin/reporte/<int:rid>/resolver')
def resolver_reporte(rid):
    if not session.get('admin'):
        return redirect('/admin/login')
    conn = get_db()
    conn.execute('UPDATE reportes SET resuelto=1 WHERE id=?', (rid,))
    conn.commit(); conn.close()
    return redirect('/admin/reportes')

@app.route('/admin/proveedor/<int:pid>/suspender')
def suspender_proveedor(pid):
    if not session.get('admin'):
        return redirect('/admin/login')
    conn = get_db()
    conn.execute('UPDATE proveedores SET activo=0 WHERE id=?', (pid,))
    conn.commit(); conn.close()
    return redirect('/admin')

@app.route('/admin/proveedor/<int:pid>/activar')
def activar_proveedor(pid):
    if not session.get('admin'):
        return redirect('/admin/login')
    conn = get_db()
    conn.execute('UPDATE proveedores SET activo=1 WHERE id=?', (pid,))
    conn.commit(); conn.close()
    return redirect('/admin')

@app.route('/admin/proveedor/<int:pid>/eliminar')
def eliminar_proveedor(pid):
    if not session.get('admin'):
        return redirect('/admin/login')
    conn = get_db()
    conn.execute('DELETE FROM proveedores WHERE id=?', (pid,))
    conn.execute('DELETE FROM calificaciones WHERE proveedor_id=?', (pid,))
    conn.execute('DELETE FROM servicios_adicionales WHERE proveedor_id=?', (pid,))
    conn.execute('DELETE FROM reportes WHERE proveedor_id=?', (pid,))
    conn.execute('DELETE FROM galeria WHERE proveedor_id=?', (pid,))
    conn.commit(); conn.close()
    return redirect('/admin')

# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)