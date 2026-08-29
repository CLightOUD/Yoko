import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const SAFE_LINK = /^(https?:\/\/|\/(?!\/)|#)/i

function safeUrl(url) {
  if (!url) return undefined
  const trimmed = String(url).trim()
  return SAFE_LINK.test(trimmed) ? trimmed : undefined
}

function MarkdownMessage({ content }) {
  return (
    <div className="markdown-body">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children, ...props }) {
            const safe = safeUrl(href)
            if (!safe) return <span>{children}</span>
            return (
              <a
                href={safe}
                target="_blank"
                rel="noopener noreferrer"
                {...props}
              >
                {children}
              </a>
            )
          },
          img() {
            // 默认不加载远程图片
            return null
          },
          // 适老样式：增大字号和间距
          h1({ children, ...props }) {
            return <h1 className="md-h1" {...props}>{children}</h1>
          },
          h2({ children, ...props }) {
            return <h2 className="md-h2" {...props}>{children}</h2>
          },
          h3({ children, ...props }) {
            return <h3 className="md-h3" {...props}>{children}</h3>
          },
          ul({ children, ...props }) {
            return <ul className="md-ul" {...props}>{children}</ul>
          },
          ol({ children, ...props }) {
            return <ol className="md-ol" {...props}>{children}</ol>
          },
          li({ children, ...props }) {
            return <li className="md-li" {...props}>{children}</li>
          },
          table({ children, ...props }) {
            return (
              <div className="md-table-wrapper">
                <table className="md-table" {...props}>{children}</table>
              </div>
            )
          },
          pre({ children, ...props }) {
            return <pre className="md-code-block" {...props}>{children}</pre>
          },
          code({ className, children, ...props }) {
            return <code className={className} {...props}>{children}</code>
          },
          blockquote({ children, ...props }) {
            return <blockquote className="md-blockquote" {...props}>{children}</blockquote>
          },
          p({ children, ...props }) {
            return <p className="md-p" {...props}>{children}</p>
          },
        }}
      >
        {content}
      </Markdown>
    </div>
  )
}

export default MarkdownMessage
