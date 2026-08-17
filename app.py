
import os, random, datetime, secrets
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_KEY"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///nexora.db").replace("postgres://","postgresql://",1)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE","0") == "1"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

class Employee(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    dob=db.Column(db.Date,nullable=False)
    password_hash=db.Column(db.String(255),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.datetime.utcnow,nullable=False)
    active=db.Column(db.Boolean,default=True,nullable=False)

class DailyResult(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    employee_id=db.Column(db.Integer,db.ForeignKey("employee.id"),nullable=False)
    work_date=db.Column(db.Date,nullable=False)
    completed=db.Column(db.Integer,default=0,nullable=False)
    correct=db.Column(db.Integer,default=0,nullable=False)
    wrong=db.Column(db.Integer,default=0,nullable=False)
    seconds=db.Column(db.Integer,default=0,nullable=False)
    __table_args__=(db.UniqueConstraint("employee_id","work_date",name="uq_employee_day"),)

def daily_records(day):
    rnd=random.Random(int(day.strftime("%Y%m%d")))
    names=["Aarav Sharma","Rohan Verma","Ananya Singh","Priya Gupta","Rahul Kumar","Neha Yadav","Vikram Mehta","Pooja Patel","Aditya Jain","Sneha Das"]
    cities=["Delhi","Mumbai","Jaipur","Lucknow","Patna","Pune","Kolkata","Bhopal","Indore","Noida"]
    out=[]
    for _ in range(200):
        n=rnd.choice(names); c=rnd.choice(cities)
        out.append({"name":n,"age":rnd.randint(18,60),"city":c,
                    "phone":"9"+"".join(str(rnd.randrange(10)) for _ in range(9)),
                    "email":n.split()[0].lower()+str(rnd.randrange(10,999))+"@example.test"})
    return out

def employee_required(f):
    @wraps(f)
    def w(*a,**kw):
        if session.get("role")!="employee": return redirect(url_for("login"))
        return f(*a,**kw)
    return w

def founder_required(f):
    @wraps(f)
    def w(*a,**kw):
        if session.get("role")!="founder": return redirect(url_for("login"))
        return f(*a,**kw)
    return w

@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")

@app.get("/health")
def health():
    return {"status":"ok"}

@app.get("/")
def home():
    if session.get("role")=="employee": return redirect(url_for("employee"))
    if session.get("role")=="founder": return redirect(url_for("founder"))
    return redirect(url_for("login"))

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        role=request.form["role"]; dob=datetime.date.fromisoformat(request.form["dob"]); password=request.form["password"]
        if role=="founder":
            founder_pw=os.environ.get("FOUNDER_PASSWORD")
            if founder_pw and secrets.compare_digest(dob.isoformat(),"1980-01-01") and secrets.compare_digest(password,founder_pw):
                session.clear(); session["role"]="founder"; return redirect(url_for("founder"))
        else:
            e=Employee.query.filter_by(dob=dob,active=True).first()
            if e and check_password_hash(e.password_hash,password):
                session.clear(); session["role"]="employee"; session["employee_id"]=e.id; return redirect(url_for("employee"))
        flash("The credentials provided could not be verified.","error")
    return render_template("login.html")

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        dob=datetime.date.fromisoformat(request.form["dob"]); p=request.form["password"]; p2=request.form["password2"]
        if len(p)<10 or p!=p2:
            flash("Use a matching password of at least 10 characters.","error")
            return render_template("register.html")
        e=Employee(dob=dob,password_hash=generate_password_hash(p))
        db.session.add(e); db.session.commit()
        session.clear(); session["role"]="employee"; session["employee_id"]=e.id
        return redirect(url_for("employee"))
    return render_template("register.html")

@app.get("/employee")
@employee_required
def employee():
    today=datetime.date.today()
    r=DailyResult.query.filter_by(employee_id=session["employee_id"],work_date=today).first()
    if not r:
        r=DailyResult(employee_id=session["employee_id"],work_date=today); db.session.add(r); db.session.commit()
    return render_template("employee.html",records=daily_records(today),completed=r.completed)

@app.post("/employee/submit")
@employee_required
def submit():
    today=datetime.date.today(); idx=int(request.form["index"])
    r=DailyResult.query.filter_by(employee_id=session["employee_id"],work_date=today).first()
    if r.completed>=200 or idx!=r.completed: return redirect(url_for("employee"))
    ref=daily_records(today)[idx]
    vals={k:request.form.get(k,"").strip() for k in ["name","city","phone","email"]}
    try: age=int(request.form.get("age",""))
    except: age=-1
    ok=vals["name"]==ref["name"] and age==ref["age"] and vals["city"]==ref["city"] and vals["phone"]==ref["phone"] and vals["email"]==ref["email"]
    r.completed+=1; r.correct+=int(ok); r.wrong=r.completed-r.correct
    r.seconds+=max(0,int(request.form.get("seconds",0)))
    db.session.commit()
    return redirect(url_for("employee"))

@app.get("/founder")
@founder_required
def founder():
    day=datetime.date.today()
    rows=db.session.query(Employee,DailyResult).outerjoin(DailyResult,(DailyResult.employee_id==Employee.id)&(DailyResult.work_date==day)).filter(Employee.active==True).all()
    return render_template("founder.html",rows=rows,day=day)

@app.get("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

with app.app_context():
    db.create_all()

if __name__=="__main__":
    app.run()
