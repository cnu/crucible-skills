# Hello World Web Application

A simple, responsive "Hello World" web application with a beautiful purple gradient background and centered typography.

## 🚀 Quick Start

### Prerequisites

- A modern web browser (Chrome, Firefox, Safari, Edge)
- No build tools or dependencies required!

### Running Locally

1. Clone or download this repository
2. Navigate to the project folder:
   ```bash
   cd hello-world
   ```
3. Open `index.html` in your browser:
   - **Option 1:** Double-click `index.html`
   - **Option 2:** Use a local server:
     ```bash
     # Python 3
     python -m http.server 8000
     
     # Node.js (with npx)
     npx serve
     
     # PHP
     php -S localhost:8000
     ```
4. Visit `http://localhost:8000` (if using a server)

## 📁 Project Structure

```
hello-world/
├── index.html      # Main HTML file
├── styles.css      # Styling and layout
└── README.md       # This file
```

## ✨ Features

- **Clean HTML5 Structure**: Semantic, accessible markup
- **Purple Gradient Background**: Beautiful linear gradient from #667eea to #764ba2
- **Centered Layout**: Perfectly centered content using Flexbox
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Modern Typography**: Clean, readable font stack
- **No Dependencies**: Pure HTML and CSS, no build process needed

## 🎨 Design Details

### Colors
- **Background Gradient**: Purple (#667eea) to Deep Purple (#764ba2)
- **Text**: White (#ffffff) with subtle text shadow
- **Responsive Breakpoints**:
  - Desktop: Default styles
  - Tablet (≤768px): Reduced font sizes
  - Mobile (≤480px): Compact layout

### Typography
- **Font Family**: System font stack (-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Oxygen, Ubuntu, sans-serif)
- **Heading**: 4rem (64px) on desktop, 2rem (32px) on mobile
- **Subtitle**: 1.25rem (20px) on desktop, 1rem (16px) on mobile
- **Font Weights**: 700 (bold) for heading, 300 (light) for subtitle

## 🌐 Browser Support

Tested and working in:
- ✅ Chrome 120+
- ✅ Firefox 121+
- ✅ Safari 17+
- ✅ Edge 120+

## 📱 Responsive Behavior

The application automatically adjusts for different screen sizes:

- **Desktop (>768px)**: Full-size typography, generous padding
- **Tablet (480px-768px)**: Reduced font sizes (2.5rem heading)
- **Mobile (<480px)**: Compact layout (2rem heading, minimal padding)

## 🛠️ Customization

### Changing the Text

Edit `index.html`:
```html
<h1 class="hello-text">Your Text Here</h1>
<p class="subtitle">Your subtitle here</p>
```

### Changing Colors

Edit `styles.css`:
```css
body {
    background: linear-gradient(135deg, #your-color-1 0%, #your-color-2 100%);
}
```

### Changing Fonts

Edit `styles.css`:
```css
body {
    font-family: 'Your Font', sans-serif;
}
```

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

## 🤝 Contributing

This is a simple Hello World example. Feel free to fork and modify for your own learning!

## 📝 Changelog

### Version 1.0.0 (2026-04-15)
- Initial release
- Created index.html with semantic HTML5 structure
- Created styles.css with gradient background and responsive design
- Added comprehensive README documentation

---

**Happy Coding!** 🎉
