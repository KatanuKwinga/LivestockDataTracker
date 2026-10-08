#Starts the development server:  python run.py
from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True reloads the app whenever you save a file and shows detailed
    # error pages. Only for development, never on a public server, because
    # those error pages reveal your code.
    app.run(debug=True)