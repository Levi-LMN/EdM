# promote_user.py
from app import app, db, User  # <-- replace with the name of the file that contains your `app`
# Example: if your file is called app.py, use: from app import app, db, User

EMAIL_TO_PROMOTE = "mukuhalevi@gmail.com"

with app.app_context():
    user = User.query.filter_by(email=EMAIL_TO_PROMOTE).first()
    if not user:
        print(f"❌ No user found with email: {EMAIL_TO_PROMOTE}")
    else:
        print(f"✅ Found user: {user.name} ({user.email}), current role: {user.role}")
        user.role = "ADMIN"
        db.session.commit()
        print(f"🎉 Role updated successfully! New role: {user.role}")
