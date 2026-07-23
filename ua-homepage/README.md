# ua-homepage

A custom landing page built from the Egonex Understand Anything design system.
No upstream dependencies — fully self-hosted and customizable.

## Quick Start

\`\`\`bash
cd ua-homepage
npm install
npm run dev       # Dev server at http://localhost:4321
npm run build     # Production build
npm run preview    # Preview production
\`\`\`

## Customization

- All Egonex links and references have been removed
- Replace \`YOUR_USERNAME/YOUR_REPO\` in Nav and Footer with your repo URL
- Edit text content directly in each component file
- The design system (fonts, colors, animations) is fully editable

## File Structure

\`\`\`
src/
  components/    # Reusable page sections
  layouts/       # Page layout templates  
  pages/         # Route files (index.astro = homepage)
  styles/        # Global CSS with design tokens
public/
  fonts/         # Self-hosted fonts (.woff2)
  images/        # Hero and screenshot images
  favicon.*      # Favicon files
\`\`\`
