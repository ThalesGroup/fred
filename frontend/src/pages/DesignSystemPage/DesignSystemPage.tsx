import styles from "./DesignSystemPage.module.css";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import Breadcrumb from "@shared/atoms/Breadcrumb/Breadcrumb.tsx";
import { Type } from "@shared/utils/Type.ts";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import Menu from "@shared/organisms/Menu/Menu.tsx";
import Select from "@shared/molecules/Select/Select.tsx";

export default function DesignSystemPage() {
  const buttonColor: Type = "secondary";

  return (
    <div className={styles.grid}>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"filled"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"outlined"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"text"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"filled"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"outlined"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"text"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"filled"} size={"small"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"outlined"} size={"small"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"text"} size={"small"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"filled"} size={"medium"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"outlined"} size={"medium"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button color={buttonColor} variant={"text"} size={"medium"} icon={{ category: "outlined", type: "Add" }}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"filled"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"outlined"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"text"} size={"small"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"filled"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"outlined"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button disabled color={buttonColor} variant={"text"} size={"medium"}>
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"filled"}
          size={"small"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"outlined"}
          size={"small"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"text"}
          size={"small"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"filled"}
          size={"medium"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"outlined"}
          size={"medium"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}>
        <Button
          disabled
          color={buttonColor}
          variant={"text"}
          size={"medium"}
          icon={{ category: "outlined", type: "Add" }}
        >
          Button
        </Button>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"filled"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"outlined"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"icon"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"filled"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"outlined"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          color={buttonColor}
          variant={"icon"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"filled"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"outlined"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"icon"}
          size={"small"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"filled"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"outlined"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}>
        <IconButton
          icon={{ category: "outlined", type: "Add" }}
          disabled
          color={buttonColor}
          variant={"icon"}
          size={"medium"}
        ></IconButton>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <TextInput label={"Input texte"} placeholder={"Placeholder"}></TextInput>
      </div>
      <div className={styles.componentCard}>
        <TextInput label={"Input texte"} placeholder={"Placeholder"} explication={"explication only"}></TextInput>
      </div>
      <div className={styles.componentCard}>
        <TextInput label={"Input texte"} placeholder={"Placeholder"} error={"error only"}></TextInput>
      </div>
      <div className={styles.componentCard}>
        <TextInput
          label={"Input texte"}
          placeholder={"Placeholder"}
          explication={"explication"}
          error={"error + explication set"}
        ></TextInput>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        {" "}
        <TextInput
          label={"Input texte"}
          placeholder={"Placeholder"}
          explication={"explication"}
          error={"error + explication set"}
          disabled
        ></TextInput>
      </div>
      <div className={styles.componentCard}>
        {" "}
        <TextInput label={"Input texte"} placeholder={"Placeholder"} explication={"explication"} disabled></TextInput>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        {" "}
        <Breadcrumb
          items={[
            {
              label: "Home",
            },
            {
              label: "Design System",
              callback: () => {
                console.log("clicked");
              },
            },
          ]}
        ></Breadcrumb>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <TextArea placeholder={"Placeholder"}></TextArea>
      </div>
      <div className={styles.componentCard}>
        <TextArea placeholder={"Placeholder"} disabled></TextArea>
      </div>
      <div className={styles.componentCard}>
        <TextArea placeholder={"Placeholder"} error={true}></TextArea>
      </div>
      <div className={styles.componentCard}>
        <TextArea placeholder={"Placeholder"} error={true} disabled></TextArea>
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <ButtonGroup
          size={"small"}
          color={"secondary"}
          items={[
            {
              label: "Button 1",
            },
            {
              label: "Button 2",
              icon: { category: "outlined", type: "Add" },
            },
            {
              label: "Button 3",
            },
            {
              label: "Button 4",
              icon: { category: "outlined", type: "Home" },
            },
            {
              label: "Button 5",
            },
          ]}
        />
      </div>
      <div className={styles.componentCard}>
        <ButtonGroup
          size={"medium"}
          color={"secondary"}
          items={[
            {
              label: "Button 1",
            },
            {
              label: "Button 2",
              icon: { category: "outlined", type: "Add" },
            },
            {
              label: "Button 3",
            },
            {
              label: "Button 4",
              icon: { category: "outlined", type: "Home" },
            },
            {
              label: "Button 5",
            },
          ]}
        />
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}>
        <Menu
          options={[
            {
              value: 1,
              label: "Button 1",
              icon: { category: "outlined", type: "Add" },
              onClick: () => console.log("Button 1"),
            },
            { value: 2, label: "Button 2", onClick: () => console.log("Button 1") },
            { value: 3, label: "Button 3", onClick: () => console.log("Button 1") },
            {
              value: 4,
              label: "Button 4",
              icon: { category: "outlined", type: "Home" },
              onClick: () => console.log("Button 1"),
            },
            { value: 5, label: "Button 5", onClick: () => console.log("Button 1") },
          ]}
          baseId={"test"}
        />
      </div>
      <div className={styles.componentCard}>
        <Select
          label="Select"
          options={[
            {
              value: 1,
              label: "Button 1",
              icon: { category: "outlined", type: "Add" },
              onClick: () => console.log("Button 1"),
            },
            { value: 2, label: "Button 2", onClick: () => console.log("Button 2") },
            { value: 3, label: "Button 3", onClick: () => console.log("Button 3") },
            {
              value: 4,
              label: "Button 4",
              icon: { category: "outlined", type: "Home" },
              onClick: () => console.log("Button 4"),
            },
            { value: 5, label: "Button 5", onClick: () => console.log("Button 5") },
          ]}
          onChange={function (value: number): void {
            throw new Error("Function not implemented.");
          }}
        />
      </div>
      <div className={styles.componentCard}>
        <Select
          label="Select"
          error={"test"}
          options={[
            {
              value: 1,
              label: "Button 1",
              icon: { category: "outlined", type: "Add" },
              onClick: () => console.log("Button 1"),
            },
            { value: 2, label: "Button 2", onClick: () => console.log("Button 2") },
            { value: 3, label: "Button 3", onClick: () => console.log("Button 3") },
            {
              value: 4,
              label: "Button 4",
              icon: { category: "outlined", type: "Home" },
              onClick: () => console.log("Button 4"),
            },
            { value: 5, label: "Button 5", onClick: () => console.log("Button 5") },
          ]}
          onChange={function (value: number): void {
            throw new Error("Function not implemented.");
          }}
        />
      </div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
      <div className={styles.componentCard}></div>
    </div>
  );
}
