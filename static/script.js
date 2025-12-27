const quoteContent = document.getElementById('quote-content');
const quoteAuthor = document.getElementById('quote-author');



if (quoteContent && quoteAuthor) {
    fetch('https://dummyjson.com/quotes/random')
      .then(response => response.json())
      .then(data => {
        quoteContent.textContent = `" ${data.quote}"`;
        quoteAuthor.textContent = `- ${data.author}`;
      })
      .catch(error => {
        console.error(error);
        quoteContent.textContent = `"A room without books is like a body without a soul."`;
        quoteAuthor.textContent = `- Marcus Tullius Cicero`;
      });
}
    