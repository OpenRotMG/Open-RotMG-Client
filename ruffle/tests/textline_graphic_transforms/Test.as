package {
    import flash.display.Sprite;
    import flash.geom.Point;
    import flash.text.engine.*;

    public class Test extends Sprite {
        public function Test() {
            var icon:Sprite = box();
            icon.x = 7;
            icon.y = 3;
            icon.scaleX = 1.5;
            var format:ElementFormat = new ElementFormat(null, 14, 0xffffff);
            var graphic:GraphicElement = new GraphicElement(icon, 16, 14, format);
            var block:TextBlock = new TextBlock(new GroupElement(new <ContentElement>[
                graphic, new TextElement("Hello", format)
            ]));
            var line:TextLine = block.createTextLine(null, 300);
            var holder:Sprite = line.getChildAt(0) as Sprite;
            trace("holder", holder !== icon && icon.parent === holder && holder.parent === line);
            trace("transform", icon.x === 7 && icon.y === 3 && icon.scaleX === 1.5);
            trace("position", holder.x === 0 && holder.y === -14 && icon.getBounds(line).y === -11);
            addChild(line);
            line.x = 100;
            line.y = 100;
            var point:Point = icon.localToGlobal(new Point());
            trace("global", point.x === 107 && point.y === 89);
            var replacement:Sprite = box();
            replacement.x = -2;
            replacement.y = 5;
            graphic.graphic = replacement;
            trace("replace", icon.parent === null && replacement.parent === holder && replacement.x === -2 && replacement.y === 5);
            graphic.graphic = null;
            trace("null", replacement.parent === null && line.numChildren === 1 && holder.numChildren === 0);
            graphic.graphic = icon;
            block.recreateTextLine(line, null, 300);
            trace("recreate", icon.parent === holder && holder.parent === line && icon.x === 7 && icon.y === 3);
            block.content = new TextElement("plain", format);
            block.recreateTextLine(line, null, 300);
            trace("detach", line.numChildren === 0 && holder.parent === null && icon.parent === holder);
            graphic.graphic = replacement;
            trace("detached replace", icon.parent === null && replacement.parent === holder && replacement.x === -2 && replacement.y === 5);
        }
        private function box():Sprite {
            var result:Sprite = new Sprite();
            result.graphics.beginFill(0xff0000);
            result.graphics.drawRect(0, 0, 14, 14);
            result.graphics.endFill();
            return result;
        }
    }
}
