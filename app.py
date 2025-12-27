from flask import Flask, render_template, request, session, redirect, url_for, flash
import pickle
import numpy as np
import requests
import json
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# Database Configuration
# Render and other cloud providers typically provide a DATABASE_URL
DATABASE_URL = os.environ.get('DATABASE_URL')

# Fallback for local development if DATABASE_URL is not set
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'root')
DB_NAME = os.environ.get('DB_NAME', 'library_db')

def get_db_connection():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    else:
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME
        )
    return conn

def init_db():
    try:
        # Connect to default 'postgres' database to create our db if it doesn't exist
        # Note: In production (Render), the DB is usually already created.
        # This part handles local setup or environments where we have admin access.
        if not DATABASE_URL:
            try:
                conn = psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, dbname='postgres')
                conn.autocommit = True
                cursor = conn.cursor()
                cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{DB_NAME}'")
                exists = cursor.fetchone()
                if not exists:
                    cursor.execute(f"CREATE DATABASE {DB_NAME}")
                    print(f"Database {DB_NAME} created.")
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"Database creation check skipped/failed: {e}")

        conn = get_db_connection()
        cwd = conn.cursor()
        
        # Create Tables
        # PostgreSQL uses SERIAL for auto-incrementing integers
        cwd.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            joined_date VARCHAR(50)
        )
        """)
        
        cwd.execute("""
        CREATE TABLE IF NOT EXISTS user_books (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            book_title VARCHAR(255),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        conn.commit()
        cwd.close()
        conn.close()
        print("Database tables initialized successfully.")
    except Exception as e:
        print(f"Database initialization failed: {e}")

# Initialize Database
init_db()

popular_df = pickle.load(open("popular.pkl", 'rb'))
pt = pickle.load(open("pt.pkl",'rb'))
books = pickle.load(open("books.pkl",'rb'))
similarity_scores = pickle.load(open("similarity_scores.pkl",'rb'))

app = Flask(__name__)
# Secret key is needed to use sessions
app.secret_key = 'a_very_secret_key_change_me'

@app.route('/welcome')
def welcome():
    return render_template('login.html')

# HOME route which also handles search and displays recommendations
@app.route('/', methods=["GET", "POST"])
def index():
    quote = "A room without books is like a body without a soul."
    author = "Marcus Tullius Cicero"
    try:
        response = requests.get("https://dummyjson.com/quotes/random", timeout=2)
        if response.status_code == 200:
            data_json = response.json()
            quote = data_json.get('quote')
            author = data_json.get('author')
    except:
        pass

    data = None
    user_input = None
    if request.method == "POST":
        user_input = request.form.get('user_input')
        if not user_input or not user_input.strip():
            return render_template('index.html', data=None, user_input=user_input, quote=quote, author=author)

        data = []
        try:
            # Find the index of the book in the pivot table
            user_input_stripped = user_input.strip()
            try:
                book_index = np.where(pt.index == user_input_stripped)[0][0]
            except IndexError:
                match = next((title for title in pt.index if title.lower() == user_input_stripped.lower()), None)
                if not match:
                    match = next((title for title in pt.index if user_input_stripped.lower() in title.lower()), None)
                if match:
                    book_index = np.where(pt.index == match)[0][0]
                else:
                    raise IndexError

            # Get top 5 similar items
            similar_items = sorted(
                list(enumerate(similarity_scores[book_index])),
                key=lambda x: x[1],
                reverse=True
            )[1:6]  # Top 5 recommendations
            for i in similar_items:
                book_title = pt.index[i[0]]
                temp_df = books[books['Book-Title'] == book_title]
                book_details = temp_df.drop_duplicates('Book-Title')
                if not book_details.empty:
                    data.append(book_details[['Book-Title', 'Book-Author', 'Image-URL-M']].values[0].tolist())
        except IndexError:
            # This will handle cases where the book is not found in pt.index
            # Fallback: Search in the main books dataset for partial matches
            try:
                mask = books['Book-Title'].str.contains(user_input_stripped, case=False, regex=False)
                matches = books[mask]
                
                if not matches.empty:
                    # If found, recommend books by the same author
                    matched_book = matches.iloc[0]
                    author = matched_book['Book-Author']
                    
                    author_books = books[books['Book-Author'] == author]
                    recommendations = author_books[author_books['Book-Title'] != matched_book['Book-Title']]
                    recommendations = recommendations.drop_duplicates('Book-Title').head(5)
                    
                    if recommendations.empty:
                        recommendations = matches.drop_duplicates('Book-Title').head(5)
                        
                    for _, row in recommendations.iterrows():
                        data.append([row['Book-Title'], row['Book-Author'], row['Image-URL-M']])
                else:
                    return render_template('not_found.html', user_input=user_input)
            except:
                return render_template('not_found.html', user_input=user_input)
    return render_template('index.html', data=data, user_input=user_input, quote=quote, author=author)

@app.route('/trending')
def trending():
    return render_template('trending.html',
        book_name = list(popular_df['Book-Title'].values),
        author=list(popular_df['Book-Author'].values),
        image=list(popular_df['Image-URL-M'].values),
        votes=list(popular_df['num_ratings'].values),
        rating=list(popular_df['avg_rating'].values)
    )

@app.route('/category')
def category():
    return render_template('category.html')

@app.route('/category/<string:category_name>')
def show_category(category_name):
    # This is a placeholder. In a real app, you would filter books by category_name.
    # Here, we'll just show different slices of the popular books for demonstration.
    if category_name == 'Fiction':
        category_df = popular_df.head(10)
    elif category_name == 'Non-Fiction':
        category_df = popular_df.iloc[10:20]
    elif category_name == 'Sci-Fi':
        category_df = popular_df.iloc[20:30]
    else:
        category_df = popular_df.tail(10) # Fallback

    return render_template('category_books.html',
        category_name=category_name,
        book_name=list(category_df['Book-Title'].values),
        author=list(category_df['Book-Author'].values),
        image=list(category_df['Image-URL-M'].values),
        votes=list(category_df['num_ratings'].values),
        rating=list(category_df['avg_rating'].values)
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user:
                session['user'] = username
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password', 'login_error')
                return redirect(url_for('login'))
        except Exception as e:
            flash(f'Database error: {str(e)}', 'login_error')
            return redirect(url_for('login'))
            
    return render_template('login.html', panel='login')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form.get('email', '')
        joined_date = datetime.now().strftime("%B %d, %Y")
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                flash('Username already exists!', 'signup_error')
                return redirect(url_for('signup'))
            
            cursor.execute("INSERT INTO users (username, password, email, joined_date) VALUES (%s, %s, %s, %s)", 
                           (username, password, email, joined_date))
            conn.commit()
            cursor.close()
            conn.close()
            
            session['user'] = username
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Signup failed: {str(e)}', 'signup_error')
            return redirect(url_for('signup'))

    return render_template('login.html', panel='signup')

@app.route('/profile')
def profile():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    username = session['user']
    book_count = 0
    email = 'Not provided'
    joined_date = 'Unknown'
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user_data = cursor.fetchone()
        
        if user_data:
            email = user_data.get('email', 'Not provided')
            joined_date = user_data.get('joined_date', 'Unknown')
            
            cursor.execute("SELECT count(*) as count FROM user_books WHERE user_id = %s", (user_data['id'],))
            res = cursor.fetchone()
            if res:
                book_count = res['count']
                
        cursor.close()
        conn.close()
    except:
        pass
    
    return render_template('profile.html', username=username, 
                           book_count=book_count,
                           email=email, joined_date=joined_date)

@app.route('/my_books')
def my_books():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    saved_books_details = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT id FROM users WHERE username = %s", (user,))
        u = cursor.fetchone()
        
        if u:
            cursor.execute("SELECT book_title FROM user_books WHERE user_id = %s", (u['id'],))
            saved_book_titles = [row['book_title'] for row in cursor.fetchall()]
            
            if saved_book_titles:
                # Filter the main books DataFrame to get details for all saved books at once
                saved_books_df = books[books['Book-Title'].isin(saved_book_titles)].drop_duplicates('Book-Title').set_index('Book-Title')
                # Reorder to match the user's saved order (if possible, though DB select doesn't guarantee order without separate ordinal column, iterating through list is safer if order matters, but here just bulk fetch)
                # To be safe against missing books in DF:
                existing_titles = [t for t in saved_book_titles if t in saved_books_df.index]
                saved_books_df = saved_books_df.reindex(existing_titles).reset_index()
                saved_books_details = saved_books_df.to_dict('records')
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(e)

    return render_template('my_books.html', saved_books=saved_books_details)

@app.route('/add_to_my_books', methods=['POST'])
def add_to_my_books():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    book_title = request.form.get('book_title')
    username = session['user']
    
    if book_title:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            res = cursor.fetchone()
            if res:
                user_id = res[0]
                cursor.execute("SELECT * FROM user_books WHERE user_id = %s AND book_title = %s", (user_id, book_title))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO user_books (user_id, book_title) VALUES (%s, %s)", (user_id, book_title))
                    conn.commit()
            
            cursor.close()
            conn.close()
        except Exception as e:
            print(e)
            
    return redirect(request.referrer or url_for('index'))

@app.route('/remove_from_my_books', methods=['POST'])
def remove_from_my_books():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    book_title = request.form.get('book_title')
    username = session['user']
    
    if book_title:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            res = cursor.fetchone()
            if res:
                user_id = res[0]
                cursor.execute("DELETE FROM user_books WHERE user_id = %s AND book_title = %s", (user_id, book_title))
                conn.commit()
                
            cursor.close()
            conn.close()
        except:
            pass
            
    return redirect(request.referrer or url_for('my_books'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
