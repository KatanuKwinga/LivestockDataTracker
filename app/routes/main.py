#General pages that aren't about accounts. 
from flask import Blueprint, render_template


main_bp = Blueprint("main", __name__)

#When someone visits /, run the function
@main_bp.route("/")
def index():
    return render_template("index.html")