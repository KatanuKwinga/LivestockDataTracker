from datetime import date

from flask_wtf import FlaskForm
from wtforms import DateField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, ValidationError

from app.farm import tag_in_use
from app.models import User


def strip_spaces(value):
    return value.strip() if isinstance(value, str) else value


def normalise_email(value):
    return value.strip().lower() if isinstance(value, str) else value


def normalise_tag(value):
    """Turn " g 014 " into "G014", so one tag can't be saved twice in two spellings."""
    return value.replace(" ", "").upper() if isinstance(value, str) else value


class FarmerRegistrationForm(FlaskForm):
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
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("An account with this email already exists.")


class LoginForm(FlaskForm):
    email = StringField("Email", filters=[normalise_email], validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


class WorkerCreationForm(FarmerRegistrationForm):
    submit = SubmitField("Add worker")


class RequestResetForm(FlaskForm):
    email = StringField("Email", filters=[normalise_email], validators=[DataRequired(), Email()])
    submit = SubmitField("Send reset link")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New password", validators=[DataRequired(), Length(min=8, message="Use at least 8 characters.")]
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("password", message="The passwords don't match.")],
    )
    submit = SubmitField("Save new password")


class AnimalForm(FlaskForm):
    """The General record: the animal's basic details."""
    tag_number = StringField("Tag number", filters=[normalise_tag], validators=[
        DataRequired(message="Every animal needs a tag number."),
        Length(max=20),
        Regexp(r"^[A-Z0-9-]+$", message="Use only letters, numbers and hyphens, for example G014."),
    ])
    gender = SelectField("Sex", choices=[("", "Choose one"), ("FEMALE", "Female"), ("MALE", "Male")],
                         validators=[DataRequired(message="Choose female or male.")])
    breed = StringField("Breed (optional)", filters=[strip_spaces], validators=[Optional(), Length(max=50)])
    date_of_birth = DateField("Date of birth (optional)", validators=[Optional()])
    description = TextAreaField("Notes (optional)", filters=[strip_spaces], validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save animal")

    def __init__(self, farm_id, animal=None, **kwargs):
        super().__init__(obj=animal, **kwargs)        # obj fills the boxes when editing
        self.farm_id = farm_id
        self.animal_id = animal.animal_id if animal else None

    def validate_tag_number(self, field):
        # When editing, the animal's own tag doesn't count as "taken".
        if tag_in_use(self.farm_id, field.data, except_animal_id=self.animal_id):
            raise ValidationError("Another animal on this farm already has this tag.")

    def validate_date_of_birth(self, field):
        if field.data and field.data > date.today():
            raise ValidationError("The date of birth can't be in the future.")
