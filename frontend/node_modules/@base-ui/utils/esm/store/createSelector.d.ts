import { Selector } from 'reselect';
type Fn = (...args: any[]) => any;
type CreateSelectorFunction = <const Args extends any[], const Selectors extends ReadonlyArray<Selector<any>>, const Combiner extends (...args: readonly [...ReturnTypes<Selectors>, ...Args]) => any>(...items: [...Selectors, Combiner]) => (...args: Selectors['length'] extends 0 ? MergeParams<ReturnTypes<Selectors>, Parameters<Combiner>> : [StateFromSelectorList<Selectors>, ...MergeParams<ReturnTypes<Selectors>, Parameters<Combiner>>]) => ReturnType<Combiner>;
type StateFromSelectorList<Selectors extends readonly any[]> = Selectors extends [f: infer F, ...other: infer R] ? StateFromSelector<F> extends StateFromSelectorList<R> ? StateFromSelector<F> : StateFromSelectorList<R> : {};
type StateFromSelector<T> = T extends ((first: infer F, ...args: any[]) => any) ? F : never;
type DropFirst<T> = T extends [any, ...infer Xs] ? Xs : [];
type ReturnTypes<FunctionsArray extends readonly Fn[]> = { [Index in keyof FunctionsArray]: FunctionsArray[Index] extends FunctionsArray[number] ? ReturnType<FunctionsArray[Index]> : never };
type MergeParams<STypes extends readonly unknown[], CTypes extends readonly unknown[]> = STypes['length'] extends 0 ? CTypes : MergeParams<DropFirst<STypes>, DropFirst<CTypes>>;
/**
 * Creates a selector function that can be used to derive values from the store's state.
 * The selector can take up to three additional arguments that can be used in the selector logic.
 * This function accepts up to six functions and combines them into a single selector function.
 * The last parameter is the combiner function that combines the results of the previous selectors.
 *
 * @example
 * const selector = createSelector(
 *  (state) => state.disabled
 * );
 *
 * @example
 * const selector = createSelector(
 *   (state) => state.disabled,
 *   (state) => state.open,
 *   (disabled, open) => ({ disabled, open })
 * );
 *
 */
export declare const createSelector: CreateSelectorFunction;
export declare const createSelectorMemoized: CreateSelectorFunction;
export {};