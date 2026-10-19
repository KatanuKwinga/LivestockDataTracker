from datetime import date

from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, FloatField, IntegerField, PasswordField, RadioField, SelectField,
                     SelectMultipleField, StringField, SubmitField, TextAreaField, widgets)
from wtforms.validators import (DataRequired, Email, EqualTo, InputRequired, Length, NumberRange, Optional, Regexp, ValidationError)

from app.farm import tag_in_use
from app.models import ProductionData, User
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



class GroupForm(FlaskForm):
    """One session of treating a group: tick spraying, deworming or vaccination."""
    date = DateField("Date", default=date.today, validators=[DataRequired(message="Enter the date.")])
    product = StringField("Product used", filters=[strip_spaces], validators=[Optional(), Length(max=100)])
    vaccine = SelectField("Vaccine", choices=[])
    animals = SelectMultipleField("Animals treated", coerce=int, choices=[],
                                  widget=widgets.ListWidget(prefix_label=False),
                                  option_widget=widgets.CheckboxInput())
    notes = TextAreaField("Notes (optional)", filters=[strip_spaces], validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save")

    def __init__(self, activity_key, species, animals, **kwargs):
        super().__init__(**kwargs)
        self.activity_key = activity_key
        self.by_id = {animal.animal_id: animal for animal in animals}
        self.animals.choices = [(animal.animal_id, animal.tag_number) for animal in animals]
        # A session uses either a vaccine (from a list) or a product (typed),
        # never both. The unused field is removed: left in, the browser would
        # never send it and its check would fail with no box to show why.
        if activity_key == "vaccinate":
            del self.product
            self.vaccine.choices = [("", "Choose the vaccine")] + [
                (name, name) for name, info in VACCINES.items() if species in info["species"]]
        else:
            del self.vaccine

    def validate_date(self, field):
        if field.data and field.data > date.today():
            raise ValidationError("The date can't be in the future.")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        if self.activity_key == "vaccinate" and not self.vaccine.data:
            self.vaccine.errors.append("Choose the vaccine that was given.")
            valid = False
        if self.activity_key != "vaccinate" and not self.product.data:
            self.product.errors.append("Write the product that was used.")
            valid = False
        if self.activity_key != "spray":
            if not self.animals.data:
                self.animals.errors.append("Tick at least one animal.")
                valid = False
            elif self.date.data:
                unborn = [self.by_id[i].tag_number for i in self.animals.data
                          if i in self.by_id and self.by_id[i].date_of_birth and self.by_id[i].date_of_birth > self.date.data]
                if unborn:
                    self.animals.errors.append(f"Not born yet on that date: {', '.join(unborn)}. Untick them.")
                    valid = False
        return valid



class SaleForm(FlaskForm):
    """A purchase or a sale of one animal. A sale takes the animal off the farm: its status becomes SOLD and it
    drops out of the herd lists. """
    transaction_type = RadioField("Bought or sold?", default="SELL",
                                  choices=[("SELL", "Sold"), ("BUY", "Bought")],
                                  validators=[DataRequired(message="Choose bought or sold.")])
    date = DateField("Date", default=date.today, validators=[DataRequired(message="Enter the date.")])
    amount = FloatField("Price in KES", validators=[
        InputRequired(message="Enter the price in KES."),
        NumberRange(min=0, message="The price can't be negative."),
    ])
    other_party = StringField("Sold to / bought from (optional)", filters=[strip_spaces],
                              validators=[Optional(), Length(max=100)])
    location = StringField("Where (optional)", filters=[strip_spaces], validators=[Optional(), Length(max=100)])
    confirm = BooleanField("I understand")
    submit = SubmitField("Save")

    def __init__(self, animal, **kwargs):
        super().__init__(**kwargs)
        self.animal = animal

    def validate_date(self, field):
        check_record_date(field, self.animal)

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        if self.transaction_type.data == "SELL" and not self.confirm.data:
            self.confirm.errors.append("Tick the box to confirm the sale.")
            valid = False
        return valid


class DeathForm(FlaskForm):
    """The death of one animal. Like a sale it takes the animal off the
    farm, so it must be confirmed."""
    date_of_death = DateField("Date of death", default=date.today,
                              validators=[DataRequired(message="Enter the date it died.")])
    cause_of_death = StringField("Cause of death", filters=[strip_spaces], validators=[
        DataRequired(message='Write the cause, or "Unknown" if nobody knows.'), Length(max=100)])
    description = TextAreaField("What happened (optional)", filters=[strip_spaces],
                                validators=[Optional(), Length(max=500)])
    confirm = BooleanField("I understand", validators=[DataRequired(message="Tick the box to confirm.")])
    submit = SubmitField("Save")

    def __init__(self, animal, **kwargs):
        super().__init__(**kwargs)
        self.animal = animal

    def validate_date_of_death(self, field):
        check_record_date(field, self.animal)



class BreedingForm(FlaskForm):
    """A breeding event for one female: she was mated (and is now expected
    to give birth), she gave birth, or she lost the pregnancy.

    A birth or a loss closes her open pregnancy record if she has one, so a
    pregnancy and its outcome stay one breeding record. Live newborns are
    counted here and registered as new animals by the route."""
    
    event = RadioField("What happened?", default="MATED", choices=[
        ("MATED", "Mated / pregnant"), ("BIRTH", "Gave birth"), ("NO_BIRTH", "Lost the pregnancy"),
    ], validators=[DataRequired(message="Choose what happened.")])
    sire = SelectField("Father (optional)", choices=[])
    mated_on = DateField("Date mated (optional)", validators=[Optional()])
    expected_date = DateField("Expected birth date (optional)", validators=[Optional()])
    birth_date = DateField("Date", validators=[Optional()])
    females_born = IntegerField("Females born alive", default=0, validators=[
        InputRequired(message="Enter a number, 0 if none."), NumberRange(min=0, max=30)])
    males_born = IntegerField("Males born alive", default=0, validators=[
        InputRequired(message="Enter a number, 0 if none."), NumberRange(min=0, max=30)])
    stillborn = IntegerField("Born dead", default=0, validators=[
        InputRequired(message="Enter a number, 0 if none."), NumberRange(min=0, max=30)])
    submit = SubmitField("Save")

    def __init__(self, dam, males, open_record, **kwargs):
        super().__init__(**kwargs)
        self.dam = dam
        self.open_record = open_record
        self.sire.choices = [("", "Not known / not on this farm")] + [
            (str(male.animal_id), male.tag_number) for male in males]

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        event, today = self.event.data, date.today()

        def problem(field, message):
            field.errors.append(message)
            return False

        if event == "MATED":
            if self.open_record is not None:
                due = self.open_record.expected_delivery_date
                valid = problem(self.event, f"{self.dam.tag_number} is already recorded as pregnant"
                                            f"{f', due {due:%d %b %Y}' if due else ''}. Record the birth or the loss instead.")
            if self.mated_on.data:
                if self.mated_on.data > today:
                    valid = problem(self.mated_on, "The date can't be in the future.")
                elif self.dam.date_of_birth and self.mated_on.data < self.dam.date_of_birth:
                    valid = problem(self.mated_on, f"{self.dam.tag_number} wasn't born yet on that date.")
                if self.expected_date.data and self.expected_date.data <= self.mated_on.data:
                    valid = problem(self.expected_date, "The birth must be after the mating.")
        else:
            if not self.birth_date.data:
                valid = problem(self.birth_date, "Enter the date.")
            else:
                try:
                    check_record_date(self.birth_date, self.dam)
                except ValidationError as error:
                    valid = problem(self.birth_date, str(error))
            if event == "BIRTH" and self.females_born.data == 0 and self.males_born.data == 0:
                valid = problem(self.females_born, 'No live young? Choose "Lost the pregnancy" instead.')
        return valid


class ProductionForm(FlaskForm):
    """One day's milk or eggs from one female. One record per day keeps the
    totals honest: two records for the same day would count it twice."""
    date = DateField("Date", default=date.today, validators=[DataRequired(message="Enter the date.")])
    amount = FloatField("Amount", validators=[
        InputRequired(message="Enter the amount, 0 if none."),
        NumberRange(min=0, message="The amount can't be negative."),
    ])
    submit = SubmitField("Save")

    def __init__(self, animal, product, **kwargs):
        super().__init__(**kwargs)
        self.animal = animal
        self.product = product            # e.g. {"item": "Milk", "metric": "L", "max": 60, ...}

    def validate_date(self, field):
        check_record_date(field, self.animal)
        earlier = ProductionData.query.filter_by(animal_id=self.animal.animal_id, date=field.data,
                                                 item=self.product["item"]).first()
        if earlier:
            raise ValidationError(f"{self.animal.tag_number} already has a {self.product['item'].lower()} record for "
                                  f"{field.data:%d %b %Y} ({earlier.yield_amount:g} {earlier.metric}). Add today's total once.")

    def validate_amount(self, field):
        most = self.product["max"]
        if field.data is not None and self.product["metric"] == "eggs" and field.data != int(field.data):
            raise ValidationError("Count whole eggs.")
        if field.data is not None and field.data > most:
            raise ValidationError(f"More than {most:g} {self.product['metric']} in a day isn't likely. Check the amount.")