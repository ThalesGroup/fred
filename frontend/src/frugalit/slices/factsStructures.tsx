// A fact is a business information that explain some usage, SLAs or
// any important information that is useful to understand the role
// of  component, a namespace or an entire application.
export enum FactType {
    DOMAIN = "domain",
    REQUIREMENT = "requirement",
    COST = "cost",
    COMPLIANCE = "compliance",
    SECURITY = "security"
}

export interface Fact {
    content: string
    user: string
    date: string
    title: string
    type?: FactType; 
}
export interface FactList {
    facts: Fact[]
}
const defaultFactList: FactList = {
    facts: []
}
export function createFactList(props: Partial<FactList> = {}): FactList {
    return { ...defaultFactList, ...props };
}   