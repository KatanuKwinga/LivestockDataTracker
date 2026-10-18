from datetime import date

from flask_wtf import FlaskForm
from wtforms import (DateField, FloatField, PasswordField, RadioField, SelectField, StringField, SubmitField, TextAreaField)
from wtforms.validators import (DataRequired, Email, EqualTo, InputRequired, Length, NumberRange, Optional, Regexp, ValidationError)

from app.farm import tag_in_use
from app.models import User
from ml.reference import VACCINES

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

def check_record_date(field, animal):
    """A record can't be dated in the future, or before the animal was born."""
    if field.data and field.data > date.today():
        raise ValidationError("The date can't be in the future.")
    if field.data and animal.date_of_birth and field.data < animal.date_of_birth:
        raise ValidationError(f"{animal.tag_number} was born on {animal.date_of_birth:%d %b %Y}, so the date can't be earlier.")


class HealthForm(FlaskForm):
    """A health record: a new illness, a follow-up treatment, a vaccination
    or a check-up."""
    record_type = RadioField("What happened?", default="ILLNESS", choices=[
        ("ILLNESS", "Fell ill"), ("TREATMENT", "Follow-up treatment"),
        ("VACCINATION", "Vaccinated"), ("CHECKUP", "Check-up"),
    ], validators=[DataRequired(message="Choose what happened.")])
    date = DateField("Date", default=date.today, validators=[DataRequired(message="Enter the date.")])
    disease = StringField("Disease or problem", filters=[strip_spaces], validators=[Optional(), Length(max=100)])
    vaccine = SelectField("Vaccine", choices=[])
    temperature = FloatField("Temperature in °C (optional)", validators=[
        Optional(),
        NumberRange(min=30, max=46, message="That reading isn't possible. Check it: 39.5, not 395."),
    ])
    treatment = StringField("Medicine given", filters=[strip_spaces], validators=[Optional(), Length(max=100)])
    dosage = StringField("Dose (optional)", filters=[strip_spaces], validators=[Optional(), Length(max=50)])
    description = TextAreaField("Notes (optional)", filters=[strip_spaces], validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save health record")

    def __init__(self, animal, **kwargs):
        super().__init__(**kwargs)
        self.animal = animal
        # Only the vaccines made for this species can be chosen.
        self.vaccine.choices = [("", "Choose the vaccine")] + [
            (name, name) for name, info in VACCINES.items() if animal.species in info["species"]]

    def validate_date(self, field):
        check_record_date(field, self.animal)

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        kind = self.record_type.data
        if kind in ("ILLNESS", "TREATMENT") and not self.disease.data:
            self.disease.errors.append("Write the disease or problem.")
            valid = False
        if kind == "TREATMENT" and not self.treatment.data:
            self.treatment.errors.append("Write the medicine that was given.")
            valid = False
        if kind == "VACCINATION" and not self.vaccine.data:
            self.vaccine.errors.append("Choose the vaccine that was given.")
            valid = False
        return valid


# The heaviest an animal of each species could weigh, in kg. Anything above
# is a typing mistake (an extra zero), not a real animal.
MAX_WEIGHT_KG = {"CATTLE": 1500, "CHICKEN": 10, "GOAT": 150, "SHEEP": 200}


class WeightForm(FlaskForm):
    """One weigh-in."""
    date = DateField("Date", default=date.today, validators=[DataRequired(message="Enter the date.")])
    weight = FloatField("Weight in kg", validators=[
        # InputRequired, not DataRequired: DataRequired treats 0 as "empty",
        # which would hide the clearer "more than 0" message.
        InputRequired(message="Enter the weight in kg."),
        NumberRange(min=0.01, message="The weight must be more than 0."),
    ])
    submit = SubmitField("Save weight")

    def __init__(self, animal, **kwargs):
        super().__init__(**kwargs)
        self.animal = animal

    def validate_date(self, field):
        check_record_date(field, self.animal)

    def validate_weight(self, field):
        heaviest = MAX_WEIGHT_KG[self.animal.species]
        if field.data and field.data > heaviest:
            raise ValidationError(f"That's heavier than any {self.animal.species.lower()} ({heaviest} kg). Check the reading.")