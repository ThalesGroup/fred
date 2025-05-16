import ReactMarkdown from 'react-markdown';
import { useTheme } from '@mui/material';

interface MarkdownRendererProps {
    content: string;
    size?: 'small' | 'medium' | 'large';
}

const MarkdownRenderer = ({ content, size = 'small' }: MarkdownRendererProps) => {
    const theme = useTheme();

    if (size === 'small') {
        return (
            <ReactMarkdown
                components={{
                    h1: ({ node, ...props }) => <h1 style={{ 
                        ...theme.typography.markdown.h1, 
                    }} {...props} />,
                    h2: ({ node, ...props }) => <h2 style={{ ...theme.typography.markdown.h2, fontSize: '0.85rem' }} {...props} />,
                    h3: ({ node, ...props }) => <h3 style={{ ...theme.typography.markdown.h3, fontSize: '0.85rem' }} {...props} />,
                    h4: ({ node, ...props }) => <h4 style={{ ...theme.typography.markdown.h4, fontSize: '0.85rem' }} {...props} />,
                    p: ({ node, ...props }) => <p style={{ ...theme.typography.markdown.p, fontSize: '0.85rem' }} {...props} />,
                    code: ({ node, ...props }) => <code style={{ ...theme.typography.markdown.code, fontSize: '0.85rem' }} {...props} />,
                    a: ({ node, ...props }) => <a style={{ ...theme.typography.markdown.a, fontSize: '0.85rem' }} {...props} />,
                    ul: ({ node, ...props }) => <ul style={{ ...theme.typography.markdown.ul, fontSize: '0.85rem' }} {...props} />,
                    li: ({ node, ...props }) => <li style={{ ...theme.typography.markdown.li, fontSize: '0.85rem' }} {...props} />,
                }}
                children={content || "No markdown content provided."}
            />
        );
    }

    return (
        <ReactMarkdown
            components={{
                h1: ({ node, ...props }) => <h1 style={{ 
                    ...theme.typography.markdown.h1, 
                }} {...props} />,
                h2: ({ node, ...props }) => <h2 style={{ ...theme.typography.markdown.h2 }} {...props} />,
                h3: ({ node, ...props }) => <h3 style={{ ...theme.typography.markdown.h3 }} {...props} />,
                h4: ({ node, ...props }) => <h4 style={{ ...theme.typography.markdown.h4 }} {...props} />,
                p: ({ node, ...props }) => <p style={{ ...theme.typography.markdown.p }} {...props} />,
                code: ({ node, ...props }) => <code style={{ ...theme.typography.markdown.code }} {...props} />,
                a: ({ node, ...props }) => <a style={{ ...theme.typography.markdown.a }} {...props} />,
                ul: ({ node, ...props }) => <ul style={{ ...theme.typography.markdown.ul }} {...props} />,
                li: ({ node, ...props }) => <li style={{ ...theme.typography.markdown.li }} {...props} />,
            }}
            children={content || "No markdown content provided."}
        />
    );
};

export default MarkdownRenderer;
