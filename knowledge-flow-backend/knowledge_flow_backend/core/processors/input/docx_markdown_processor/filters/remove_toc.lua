in_toc_section = false

function Header(el)
  if el.attr and el.attr.classes then
    for i, class in ipairs(el.attr.classes) do
      if class == "TOC-Heading" then
        in_toc_section = true
        return {} -- Remove the header
      end
    end
  end
  -- If we encounter another header and we are in a TOC section, stop removing
  if in_toc_section then
    in_toc_section = false
  end
  return el
end

function Block(el)
  if in_toc_section then
    return {}
  end
  return el
end

function Pandoc(el)
  local blocks = {}
  for _, block in ipairs(el.blocks) do
    if block.t == "Header" then
      block = Header(block)
      if block.t == "Header" then
        in_toc_section = false
      end
    end
    if not in_toc_section then
      table.insert(blocks, block)
    elseif block.t == "Header" then
      in_toc_section = false
    end
  end
  el.blocks = blocks
  return el
end
