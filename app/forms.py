"""Web forms.

Flask-WTF gives every form two protections:
- CSRF protection: a hidden secret token proves the form was submitted from
  our own page, not by another website tricking the user's browser into
  sending it.
- Server-side validation: the rules below run on the server, so they can't be
  skipped by editing the page or switching off JavaScript.
"""
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError

from app.models import User


# Filters tidy what the user typed BEFORE the validators check it. Without
# them, " jane@example.com" (with a space, which phone keyboards often add)
# fails the email check, and "Jane@Example.com" could sign up a second time
# next to "jane@example.com".
def strip_spaces(value):
    return value.strip() if isinstance(value, str) else value


def normalise_email(value):
    return value.strip().lower() if isinstance(value, str) else value


class FarmerRegistrationForm(FlaskForm):
    """The only way to sign up. Workers never register themselves: a farmer
    creates their accounts (Batch 6), so every worker belongs to a farm."""

    name = StringField("Full name", filters=[strip_spaces], validators=[DataRequired(), Length(max=100)])
    email = StringField("Email", filters=[normalise_email], validators=[DataRequired(), Email(), Length(max=150)])
    phone = StringField("Phone (optional)", filters=[strip_spaces], validators=[Optional(), Length(max=20)])
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=8, message="Use at least 8 characters.")]
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="The passwords don't match.")],
    )
    submit = SubmitField("Create account")

    def validate_email(self, field):
        # WTForms runs any method called validate_<fieldname> automatically,
        # so this error appears right under the email box.
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("An account with this email already exists.")



class LoginForm(FlaskForm):
    # The same email filter as registration, so " Jane@Example.com " finds
    # the account saved as "jane@example.com".
    email = StringField("Email", filters=[normalise_email], validators=[DataRequired(), Email()])
    # No length rule here: when logging in we only check whether the
    # password is right, not whether it would be a good new password.
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")