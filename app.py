from flask import Flask, render_template, request, session, redirect, url_for, flash
import pickle
import numpy as np
import requests
import json
import os
from datetime import datetime

USERS_FILE = 'users.json'

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_users():
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

users = load_users()

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
        user_data = users.get(username)
        if user_data and user_data['password'] == password:
            session['user'] = username
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'login_error')
            return redirect(url_for('login'))
    return render_template('login.html', panel='login')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users:
            flash('Username already exists!', 'signup_error')
            return redirect(url_for('signup'))
        
        users[username] = {
            'password': password,
            'email': request.form.get('email', ''),
            'joined_date': datetime.now().strftime("%B %d, %Y"),
            'my_books': []
        }
        save_users()
        session['user'] = username
        return redirect(url_for('index'))
    return render_template('login.html', panel='signup')

@app.route('/profile')
def profile():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = session['user']
    user_data = users.get(user, {})
    
    email = user_data.get('email', 'Not provided')
    joined_date = user_data.get('joined_date', 'Unknown')
    
    return render_template('profile.html', username=user, 
                           book_count=len(user_data.get('my_books', [])),
                           email=email, joined_date=joined_date)

@app.route('/my_books')
def my_books():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    saved_book_titles = users.get(user, {}).get('my_books', [])
    
    saved_books_details = []
    if saved_book_titles:
        # Filter the main books DataFrame to get details for all saved books at once
        saved_books_df = books[books['Book-Title'].isin(saved_book_titles)].drop_duplicates('Book-Title').set_index('Book-Title')
        # Reorder to match the user's saved order
        saved_books_df = saved_books_df.reindex(saved_book_titles).reset_index()
        saved_books_details = saved_books_df.to_dict('records')

    return render_template('my_books.html', saved_books=saved_books_details)

@app.route('/add_to_my_books', methods=['POST'])
def add_to_my_books():
    if 'user' not in session:
        return redirect(url_for('login'))
    book_title = request.form.get('book_title')
    if book_title and book_title not in users[session['user']]['my_books']:
        users[session['user']]['my_books'].append(book_title)
        save_users()
    return redirect(request.referrer or url_for('index'))

@app.route('/remove_from_my_books', methods=['POST'])
def remove_from_my_books():
    if 'user' not in session:
        return redirect(url_for('login'))
    book_title = request.form.get('book_title')
    if book_title and book_title in users[session['user']]['my_books']:
        users[session['user']]['my_books'].remove(book_title)
        save_users()
    return redirect(request.referrer or url_for('my_books'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
