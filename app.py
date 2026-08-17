import os
import random
import datetime
import secrets

from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect


app = Flask(__name__)

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

app.config["SECRET_KEY"] = (
    os.environ.get("SECRET_KEY")
    or "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_KEY"
)

database_url = os.environ.get(
    "DATABASE_URL",
    "sqlite:///nexora.db"
)

# Railway / Render sometimes provide postgres://
database_url = database_url.replace(
    "postgres://",
    "postgresql://",
    1
)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("COOKIE_SECURE", "0") == "1"
)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


db = SQLAlchemy(app)
csrf = CSRFProtect(app)


# ---------------------------------------------------------
# EMPLOYEE MODEL
# ---------------------------------------------------------

class Employee(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    employee_name = db.Column(
        db.String(150),
        nullable=False
    )

    dob = db.Column(
        db.Date,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        nullable=False
    )

    active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )


# ---------------------------------------------------------
# DAILY RESULT MODEL
# ---------------------------------------------------------

class DailyResult(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("employee.id"),
        nullable=False
    )

    work_date = db.Column(
        db.Date,
        nullable=False
    )

    completed = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    correct = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    wrong = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    seconds = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "employee_id",
            "work_date",
            name="uq_employee_day"
        ),
    )


# ---------------------------------------------------------
# DATABASE SETUP / MIGRATION
# ---------------------------------------------------------

def setup_database():
    """
    Creates tables and also adds employee_name to an old
    database if the old Employee table does not have it.
    """

    db.create_all()

    try:
        inspector = db.inspect(db.engine)

        tables = inspector.get_table_names()

        if "employee" not in tables:
            return

        columns = [
            column["name"]
            for column in inspector.get_columns("employee")
        ]

        # Old database compatibility:
        # add employee_name if it does not already exist
        if "employee_name" not in columns:

            with db.engine.begin() as connection:

                connection.exec_driver_sql(
                    """
                    ALTER TABLE employee
                    ADD COLUMN employee_name VARCHAR(150)
                    """
                )

                # Give old employees a temporary name
                connection.exec_driver_sql(
                    """
                    UPDATE employee
                    SET employee_name =
                        'Employee ' || CAST(id AS VARCHAR)
                    WHERE employee_name IS NULL
                    """
                )

    except Exception as error:
        print(
            "Database migration warning:",
            error
        )


# ---------------------------------------------------------
# DAILY SIMULATED RECORDS
# ---------------------------------------------------------

def daily_records(day):

    rnd = random.Random(
        int(day.strftime("%Y%m%d"))
    )

    names = [
        "Aarav Sharma",
        "Rohan Verma",
        "Ananya Singh",
        "Priya Gupta",
        "Rahul Kumar",
        "Neha Yadav",
        "Vikram Mehta",
        "Pooja Patel",
        "Aditya Jain",
        "Sneha Das",
    ]

    cities = [
        "Delhi",
        "Mumbai",
        "Jaipur",
        "Lucknow",
        "Patna",
        "Pune",
        "Kolkata",
        "Bhopal",
        "Indore",
        "Noida",
    ]

    out = []

    for _ in range(200):

        n = rnd.choice(names)
        c = rnd.choice(cities)

        out.append(
            {
                "name": n,
                "age": rnd.randint(18, 60),
                "city": c,
                "phone": "9"
                + "".join(
                    str(rnd.randrange(10))
                    for _ in range(9)
                ),
                "email":
                    n.split()[0].lower()
                    + str(rnd.randrange(10, 999))
                    + "@example.test",
            }
        )

    return out


# ---------------------------------------------------------
# LOGIN PROTECTION
# ---------------------------------------------------------

def employee_required(f):

    @wraps(f)
    def w(*args, **kwargs):

        if session.get("role") != "employee":
            return redirect(
                url_for("login")
            )

        return f(*args, **kwargs)

    return w


def founder_required(f):

    @wraps(f)
    def w(*args, **kwargs):

        if session.get("role") != "founder":
            return redirect(
                url_for("login")
            )

        return f(*args, **kwargs)

    return w


# ---------------------------------------------------------
# INIT DATABASE COMMAND
# ---------------------------------------------------------

@app.cli.command("init-db")
def init_db():

    setup_database()

    print(
        "Database initialized successfully."
    )


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------

@app.get("/health")
def health():

    return {
        "status": "ok"
    }


# ---------------------------------------------------------
# HOME
# ---------------------------------------------------------

@app.get("/")
def home():

    if session.get("role") == "employee":
        return redirect(
            url_for("employee")
        )

    if session.get("role") == "founder":
        return redirect(
            url_for("founder")
        )

    return redirect(
        url_for("login")
    )


# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        role = request.form["role"]

        try:
            dob = datetime.date.fromisoformat(
                request.form["dob"]
            )
        except ValueError:

            flash(
                "Please enter a valid date of birth.",
                "error"
            )

            return render_template(
                "login.html"
            )

        password = request.form["password"]

        # -------------------------
        # FOUNDER LOGIN
        # -------------------------

        if role == "founder":

            founder_pw = os.environ.get(
                "FOUNDER_PASSWORD"
            )

            if (
                founder_pw
                and secrets.compare_digest(
                    dob.isoformat(),
                    "1980-01-01"
                )
                and secrets.compare_digest(
                    password,
                    founder_pw
                )
            ):

                session.clear()

                session["role"] = "founder"

                return redirect(
                    url_for("founder")
                )

        # -------------------------
        # EMPLOYEE LOGIN
        # -------------------------

        else:

            e = Employee.query.filter_by(
                dob=dob,
                active=True
            ).first()

            if (
                e
                and check_password_hash(
                    e.password_hash,
                    password
                )
            ):

                session.clear()

                session["role"] = "employee"

                session["employee_id"] = e.id

                return redirect(
                    url_for("employee")
                )

        flash(
            "The credentials provided could not be verified.",
            "error"
        )

    return render_template(
        "login.html"
    )


# ---------------------------------------------------------
# EMPLOYEE REGISTRATION
# ---------------------------------------------------------

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        # -------------------------
        # GET FORM DATA
        # -------------------------

        employee_name = (
            request.form
            .get("employee_name", "")
            .strip()
        )

        dob_value = (
            request.form
            .get("dob", "")
            .strip()
        )

        password = request.form.get(
            "password",
            ""
        )

        password2 = request.form.get(
            "password2",
            ""
        )

        # -------------------------
        # NAME VALIDATION
        # -------------------------

        if not employee_name:

            flash(
                "Employee name is required.",
                "error"
            )

            return render_template(
                "register.html"
            )

        if len(employee_name) < 2:

            flash(
                "Please enter a valid employee name.",
                "error"
            )

            return render_template(
                "register.html"
            )

        if len(employee_name) > 150:

            flash(
                "Employee name is too long.",
                "error"
            )

            return render_template(
                "register.html"
            )

        # -------------------------
        # DOB VALIDATION
        # -------------------------

        try:

            dob = datetime.date.fromisoformat(
                dob_value
            )

        except ValueError:

            flash(
                "Please enter a valid date of birth.",
                "error"
            )

            return render_template(
                "register.html"
            )

        # -------------------------
        # PASSWORD VALIDATION
        # -------------------------

        if len(password) < 10:

            flash(
                "Password must be at least 10 characters.",
                "error"
            )

            return render_template(
                "register.html"
            )

        if password != password2:

            flash(
                "Passwords do not match.",
                "error"
            )

            return render_template(
                "register.html"
            )

        # -------------------------
        # CREATE EMPLOYEE
        # -------------------------

        e = Employee(
            employee_name=employee_name,
            dob=dob,
            password_hash=generate_password_hash(
                password
            )
        )

        db.session.add(e)

        db.session.commit()

        # -------------------------
        # LOGIN AFTER REGISTRATION
        # -------------------------

        session.clear()

        session["role"] = "employee"

        session["employee_id"] = e.id

        return redirect(
            url_for("employee")
        )

    return render_template(
        "register.html"
    )


# ---------------------------------------------------------
# EMPLOYEE DASHBOARD
# ---------------------------------------------------------

@app.get("/employee")
@employee_required
def employee():

    today = datetime.date.today()

    employee_id = session["employee_id"]

    r = DailyResult.query.filter_by(
        employee_id=employee_id,
        work_date=today
    ).first()

    if not r:

        r = DailyResult(
            employee_id=employee_id,
            work_date=today
        )

        db.session.add(r)

        db.session.commit()

    current_employee = Employee.query.get(
        employee_id
    )

    return render_template(
        "employee.html",
        records=daily_records(today),
        completed=r.completed,
        employee=current_employee
    )


# ---------------------------------------------------------
# EMPLOYEE SUBMIT
# ---------------------------------------------------------

@app.post("/employee/submit")
@employee_required
def submit():

    today = datetime.date.today()

    idx = int(
        request.form["index"]
    )

    employee_id = session[
        "employee_id"
    ]

    r = DailyResult.query.filter_by(
        employee_id=employee_id,
        work_date=today
    ).first()

    if not r:

        r = DailyResult(
            employee_id=employee_id,
            work_date=today
        )

        db.session.add(r)

        db.session.commit()

    if r.completed >= 200:

        return redirect(
            url_for("employee")
        )

    if idx != r.completed:

        return redirect(
            url_for("employee")
        )

    ref = daily_records(today)[idx]

    vals = {
        k: request.form.get(
            k,
            ""
        ).strip()
        for k in [
            "name",
            "city",
            "phone",
            "email"
        ]
    }

    try:

        age = int(
            request.form.get(
                "age",
                ""
            )
        )

    except ValueError:

        age = -1

    ok = (
        vals["name"] == ref["name"]
        and age == ref["age"]
        and vals["city"] == ref["city"]
        and vals["phone"] == ref["phone"]
        and vals["email"] == ref["email"]
    )

    r.completed += 1

    r.correct += int(ok)

    r.wrong = (
        r.completed - r.correct
    )

    r.seconds += max(
        0,
        int(
            request.form.get(
                "seconds",
                0
            )
        )
    )

    db.session.commit()

    return redirect(
        url_for("employee")
    )


# ---------------------------------------------------------
# FOUNDER DASHBOARD
# ---------------------------------------------------------

@app.get("/founder")
@founder_required
def founder():

    day = datetime.date.today()

    rows = (
        db.session
        .query(Employee, DailyResult)
        .outerjoin(
            DailyResult,
            (
                DailyResult.employee_id
                == Employee.id
            )
            & (
                DailyResult.work_date
                == day
            )
        )
        .filter(
            Employee.active == True
        )
        .order_by(
            Employee.id.asc()
        )
        .all()
    )

    return render_template(
        "founder.html",
        rows=rows,
        day=day
    )


# ---------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------

@app.get("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ---------------------------------------------------------
# STARTUP
# ---------------------------------------------------------

with app.app_context():

    setup_database()


if __name__ == "__main__":

    app.run()
